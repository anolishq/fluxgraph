#include "fluxgraph/graph/compiler.hpp"
#include <gtest/gtest.h>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using namespace fluxgraph;

namespace {

double variant_to_double(const ParamValue &value, const std::string &path) {
  if (std::holds_alternative<double>(value)) {
    return std::get<double>(value);
  }
  if (std::holds_alternative<int64_t>(value)) {
    return static_cast<double>(std::get<int64_t>(value));
  }
  throw std::runtime_error("Expected numeric value at " + path);
}

std::string variant_to_string(const ParamValue &value, const std::string &path) {
  if (std::holds_alternative<std::string>(value)) {
    return std::get<std::string>(value);
  }
  throw std::runtime_error("Expected string value at " + path);
}

class AffineTestTransform : public ITransform {
public:
  explicit AffineTestTransform(double bias) : bias_(bias) {}

  double apply(double input, double /*dt*/) override {
    return input * 2.0 + bias_;
  }
  void reset() override {}
  ITransform *clone() const override { return new AffineTestTransform(*this); }

private:
  double bias_ = 0.0;
};

class ConstantSignalModel : public IModel {
public:
  ConstantSignalModel(std::string id, SignalId output, double value,
                      std::string unit)
      : id_(std::move(id)), output_(output), value_(value),
        unit_(std::move(unit)) {}

  void tick(double /*dt*/, SignalStore &store) override {
    store.write(output_, value_, unit_);
  }

  void reset() override {}

  double compute_stability_limit() const override {
    return std::numeric_limits<double>::infinity();
  }

  std::string describe() const override {
    return "ConstantSignalModel(" + id_ + ")";
  }
  std::vector<SignalId> output_signal_ids() const override { return {output_}; }

private:
  std::string id_;
  SignalId output_ = INVALID_SIGNAL;
  double value_ = 0.0;
  std::string unit_;
};

} // namespace

TEST(GraphCompilerTest, ParseLinearTransform) {
  TransformSpec spec;
  spec.type = "linear";
  spec.params["scale"] = 2.0;
  spec.params["offset"] = 5.0;

  GraphCompiler compiler;
  ITransform *tf = compiler.parse_transform(spec);

  EXPECT_NE(tf, nullptr);
  EXPECT_EQ(tf->apply(10.0, 0.1), 25.0); // 2*10 + 5

  delete tf;
}

TEST(GraphCompilerTest, ParseFirstOrderLag) {
  TransformSpec spec;
  spec.type = "first_order_lag";
  spec.params["tau_s"] = 1.0;

  GraphCompiler compiler;
  ITransform *tf = compiler.parse_transform(spec);

  EXPECT_NE(tf, nullptr);
  double y = tf->apply(100.0, 0.1);
  EXPECT_EQ(y, 100.0); // First call initializes

  delete tf;
}

TEST(GraphCompilerTest, UnknownTransformThrows) {
  TransformSpec spec;
  spec.type = "unknown_transform";

  GraphCompiler compiler;
  EXPECT_THROW(compiler.parse_transform(spec), std::runtime_error);
}

TEST(GraphCompilerTest, RegisterTransformFactoryRejectsInvalidInputs) {
  GraphCompiler::TransformFactory empty_factory;

  EXPECT_THROW(GraphCompiler::register_transform_factory(
                   "",
                   [](const TransformSpec &) {
                     return std::make_unique<AffineTestTransform>(0.0);
                   }),
               std::invalid_argument);
  EXPECT_THROW(GraphCompiler::register_transform_factory("test.empty_factory",
                                                         empty_factory),
               std::invalid_argument);
}

TEST(GraphCompilerTest, RegisterTransformFactorySupportsExternalTypes) {
  const std::string type = "test.custom_affine_transform";
  if (!GraphCompiler::is_transform_registered(type)) {
    GraphCompiler::register_transform_factory(
        type, [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
          auto bias_it = spec.params.find("bias");
          if (bias_it == spec.params.end()) {
            throw std::runtime_error("Missing parameter: bias");
          }
          return std::make_unique<AffineTestTransform>(
              variant_to_double(bias_it->second, "transform[test]/bias"));
        });
  }

  TransformSpec spec;
  spec.type = type;
  spec.params["bias"] = 3.5;

  GraphCompiler compiler;
  std::unique_ptr<ITransform> tf(compiler.parse_transform(spec));
  ASSERT_NE(tf, nullptr);
  EXPECT_DOUBLE_EQ(tf->apply(2.0, 0.1), 7.5);
}

TEST(GraphCompilerTest, RegisterTransformFactoryRejectsDuplicateType) {
  const std::string type = "test.duplicate_transform";
  if (!GraphCompiler::is_transform_registered(type)) {
    GraphCompiler::register_transform_factory(
        type, [](const TransformSpec &) -> std::unique_ptr<ITransform> {
          return std::make_unique<AffineTestTransform>(0.0);
        });
  }

  EXPECT_THROW(GraphCompiler::register_transform_factory(
                   type,
                   [](const TransformSpec &) -> std::unique_ptr<ITransform> {
                     return std::make_unique<AffineTestTransform>(1.0);
                   }),
               std::runtime_error);
}

TEST(GraphCompilerTest, CompileSimpleGraph) {
  GraphSpec spec;

  EdgeSpec edge;
  edge.source_path = "input/value";
  edge.target_path = "output/value";
  edge.transform.type = "linear";
  edge.transform.params["scale"] = 2.0;
  edge.transform.params["offset"] = 0.0;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;

  GraphCompiler compiler;
  CompiledProgram program = compiler.compile(spec, signal_ns, func_ns);

  EXPECT_EQ(program.edges.size(), 1);
  EXPECT_NE(program.edges[0].transform, nullptr);
  EXPECT_EQ(program.required_signal_capacity, signal_ns.size());
  EXPECT_EQ(program.required_command_capacity, 0u);
}

TEST(GraphCompilerTest, TopologicalSortPreservesOrder) {
  GraphSpec spec;

  // Create a chain: A -> B -> C
  EdgeSpec edge1;
  edge1.source_path = "A";
  edge1.target_path = "B";
  edge1.transform.type = "linear";
  edge1.transform.params["scale"] = 1.0;
  edge1.transform.params["offset"] = 0.0;

  EdgeSpec edge2;
  edge2.source_path = "B";
  edge2.target_path = "C";
  edge2.transform.type = "linear";
  edge2.transform.params["scale"] = 1.0;
  edge2.transform.params["offset"] = 0.0;

  // Add in reverse order to test sorting
  spec.edges.push_back(edge2);
  spec.edges.push_back(edge1);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;

  GraphCompiler compiler;
  CompiledProgram program = compiler.compile(spec, signal_ns, func_ns);

  EXPECT_EQ(program.edges.size(), 2);
  // After topological sort, edge1 (A->B) should come before edge2 (B->C)
}

TEST(GraphCompilerTest, CycleDetection) {
  GraphSpec spec;

  // Create a cycle: A -> B -> A
  EdgeSpec edge1;
  edge1.source_path = "A";
  edge1.target_path = "B";
  edge1.transform.type = "linear";
  edge1.transform.params["scale"] = 1.0;
  edge1.transform.params["offset"] = 0.0;

  EdgeSpec edge2;
  edge2.source_path = "B";
  edge2.target_path = "A";
  edge2.transform.type = "linear";
  edge2.transform.params["scale"] = 1.0;
  edge2.transform.params["offset"] = 0.0;

  spec.edges.push_back(edge1);
  spec.edges.push_back(edge2);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;

  GraphCompiler compiler;
  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns), std::runtime_error);
}

TEST(GraphCompilerTest, ParseThermalMassModel) {
  ModelSpec spec;
  spec.id = "chamber_air";
  spec.type = "thermal_mass";
  spec.params["thermal_mass"] = 1000.0;
  spec.params["heat_transfer_coeff"] = 10.0;
  spec.params["initial_temp"] = 25.0;
  spec.params["temp_signal"] = std::string("chamber_air/temperature");
  spec.params["power_signal"] = std::string("chamber_air/power");
  spec.params["ambient_signal"] = std::string("chamber_air/ambient");

  SignalNamespace ns;
  GraphCompiler compiler;
  IModel *model = compiler.parse_model(spec, ns);

  EXPECT_NE(model, nullptr);
  EXPECT_NE(model->describe().find("ThermalMass"), std::string::npos);

  delete model;
}

TEST(GraphCompilerTest, ParseThermalMassModelWithRk4) {
  ModelSpec spec;
  spec.id = "chamber_air";
  spec.type = "thermal_mass";
  spec.params["thermal_mass"] = 1000.0;
  spec.params["heat_transfer_coeff"] = 10.0;
  spec.params["initial_temp"] = 25.0;
  spec.params["temp_signal"] = std::string("chamber_air/temperature");
  spec.params["power_signal"] = std::string("chamber_air/power");
  spec.params["ambient_signal"] = std::string("chamber_air/ambient");
  spec.params["integration_method"] = std::string("rk4");

  SignalNamespace ns;
  GraphCompiler compiler;
  std::unique_ptr<IModel> model(compiler.parse_model(spec, ns));

  ASSERT_NE(model, nullptr);
  EXPECT_NE(model->describe().find("method=rk4"), std::string::npos);
}

TEST(GraphCompilerTest,
     ParseThermalMassModelWithInvalidIntegrationMethodThrows) {
  ModelSpec spec;
  spec.id = "chamber_air";
  spec.type = "thermal_mass";
  spec.params["thermal_mass"] = 1000.0;
  spec.params["heat_transfer_coeff"] = 10.0;
  spec.params["initial_temp"] = 25.0;
  spec.params["temp_signal"] = std::string("chamber_air/temperature");
  spec.params["power_signal"] = std::string("chamber_air/power");
  spec.params["ambient_signal"] = std::string("chamber_air/ambient");
  spec.params["integration_method"] = std::string("invalid_method");

  SignalNamespace ns;
  GraphCompiler compiler;
  EXPECT_THROW(compiler.parse_model(spec, ns), std::runtime_error);
}

TEST(GraphCompilerTest, ParseThermalMassModelWithNonPositiveThermalMassThrows) {
  ModelSpec spec;
  spec.id = "chamber_air";
  spec.type = "thermal_mass";
  spec.params["thermal_mass"] = 0.0;
  spec.params["heat_transfer_coeff"] = 10.0;
  spec.params["initial_temp"] = 25.0;
  spec.params["temp_signal"] = std::string("chamber_air/temperature");
  spec.params["power_signal"] = std::string("chamber_air/power");
  spec.params["ambient_signal"] = std::string("chamber_air/ambient");

  SignalNamespace ns;
  GraphCompiler compiler;
  try {
    std::unique_ptr<IModel> model(compiler.parse_model(spec, ns));
    (void)model;
    FAIL() << "Expected runtime_error for non-positive thermal_mass";
  } catch (const std::runtime_error &e) {
    EXPECT_NE(std::string(e.what()).find("/thermal_mass"), std::string::npos);
  }
}

TEST(GraphCompilerTest,
     ParseThermalMassModelWithNonPositiveHeatTransferCoeffThrows) {
  ModelSpec spec;
  spec.id = "chamber_air";
  spec.type = "thermal_mass";
  spec.params["thermal_mass"] = 1000.0;
  spec.params["heat_transfer_coeff"] = 0.0;
  spec.params["initial_temp"] = 25.0;
  spec.params["temp_signal"] = std::string("chamber_air/temperature");
  spec.params["power_signal"] = std::string("chamber_air/power");
  spec.params["ambient_signal"] = std::string("chamber_air/ambient");

  SignalNamespace ns;
  GraphCompiler compiler;
  try {
    std::unique_ptr<IModel> model(compiler.parse_model(spec, ns));
    (void)model;
    FAIL() << "Expected runtime_error for non-positive heat_transfer_coeff";
  } catch (const std::runtime_error &e) {
    EXPECT_NE(std::string(e.what()).find("/heat_transfer_coeff"),
              std::string::npos);
  }
}

TEST(GraphCompilerTest, ParseThermalMassModelWithNonFiniteInitialTempThrows) {
  ModelSpec spec;
  spec.id = "chamber_air";
  spec.type = "thermal_mass";
  spec.params["thermal_mass"] = 1000.0;
  spec.params["heat_transfer_coeff"] = 10.0;
  spec.params["initial_temp"] = std::numeric_limits<double>::infinity();
  spec.params["temp_signal"] = std::string("chamber_air/temperature");
  spec.params["power_signal"] = std::string("chamber_air/power");
  spec.params["ambient_signal"] = std::string("chamber_air/ambient");

  SignalNamespace ns;
  GraphCompiler compiler;
  try {
    std::unique_ptr<IModel> model(compiler.parse_model(spec, ns));
    (void)model;
    FAIL() << "Expected runtime_error for non-finite initial_temp";
  } catch (const std::runtime_error &e) {
    EXPECT_NE(std::string(e.what()).find("/initial_temp"), std::string::npos);
  }
}

TEST(GraphCompilerTest, ParseFirstOrderProcessModel) {
  ModelSpec spec;
  spec.id = "pt1";
  spec.type = "first_order_process";
  spec.params["gain"] = 2.0;
  spec.params["tau_s"] = 1.0;
  spec.params["initial_output"] = 0.0;
  spec.params["output_signal"] = std::string("pt1.y");
  spec.params["input_signal"] = std::string("pt1.u");

  SignalNamespace ns;
  GraphCompiler compiler;
  std::unique_ptr<IModel> model(compiler.parse_model(spec, ns));

  ASSERT_NE(model, nullptr);
  EXPECT_NE(model->describe().find("FirstOrderProcess"), std::string::npos);
}

TEST(GraphCompilerTest,
     ParseFirstOrderProcessModelWithInvalidIntegrationMethodThrows) {
  ModelSpec spec;
  spec.id = "pt1";
  spec.type = "first_order_process";
  spec.params["gain"] = 2.0;
  spec.params["tau_s"] = 1.0;
  spec.params["initial_output"] = 0.0;
  spec.params["output_signal"] = std::string("pt1.y");
  spec.params["input_signal"] = std::string("pt1.u");
  spec.params["integration_method"] = std::string("invalid_method");

  SignalNamespace ns;
  GraphCompiler compiler;
  EXPECT_THROW(compiler.parse_model(spec, ns), std::runtime_error);
}

TEST(GraphCompilerTest, ParseSecondOrderProcessModel) {
  ModelSpec spec;
  spec.id = "pt2";
  spec.type = "second_order_process";
  spec.params["gain"] = 2.0;
  spec.params["zeta"] = 0.5;
  spec.params["omega_n_rad_s"] = 3.0;
  spec.params["initial_output"] = 0.0;
  spec.params["initial_output_rate"] = 0.0;
  spec.params["output_signal"] = std::string("pt2.y");
  spec.params["input_signal"] = std::string("pt2.u");

  SignalNamespace ns;
  GraphCompiler compiler;
  std::unique_ptr<IModel> model(compiler.parse_model(spec, ns));

  ASSERT_NE(model, nullptr);
  EXPECT_NE(model->describe().find("SecondOrderProcess"), std::string::npos);
}

TEST(GraphCompilerTest,
     ParseSecondOrderProcessModelWithInvalidIntegrationMethodThrows) {
  ModelSpec spec;
  spec.id = "pt2";
  spec.type = "second_order_process";
  spec.params["gain"] = 2.0;
  spec.params["zeta"] = 0.5;
  spec.params["omega_n_rad_s"] = 3.0;
  spec.params["initial_output"] = 0.0;
  spec.params["initial_output_rate"] = 0.0;
  spec.params["output_signal"] = std::string("pt2.y");
  spec.params["input_signal"] = std::string("pt2.u");
  spec.params["integration_method"] = std::string("invalid_method");

  SignalNamespace ns;
  GraphCompiler compiler;
  EXPECT_THROW(compiler.parse_model(spec, ns), std::runtime_error);
}

TEST(GraphCompilerTest, ParseMassSpringDamperModel) {
  ModelSpec spec;
  spec.id = "msd";
  spec.type = "mass_spring_damper";
  spec.params["mass"] = 1.0;
  spec.params["damping_coeff"] = 2.0;
  spec.params["spring_constant"] = 20.0;
  spec.params["initial_position"] = 0.0;
  spec.params["initial_velocity"] = 0.0;
  spec.params["position_signal"] = std::string("msd.x");
  spec.params["velocity_signal"] = std::string("msd.v");
  spec.params["force_signal"] = std::string("msd.F");

  SignalNamespace ns;
  GraphCompiler compiler;
  std::unique_ptr<IModel> model(compiler.parse_model(spec, ns));

  ASSERT_NE(model, nullptr);
  EXPECT_NE(model->describe().find("MassSpringDamper"), std::string::npos);
}

TEST(GraphCompilerTest,
     ParseMassSpringDamperModelWithInvalidIntegrationMethodThrows) {
  ModelSpec spec;
  spec.id = "msd";
  spec.type = "mass_spring_damper";
  spec.params["mass"] = 1.0;
  spec.params["damping_coeff"] = 2.0;
  spec.params["spring_constant"] = 20.0;
  spec.params["initial_position"] = 0.0;
  spec.params["initial_velocity"] = 0.0;
  spec.params["position_signal"] = std::string("msd.x");
  spec.params["velocity_signal"] = std::string("msd.v");
  spec.params["force_signal"] = std::string("msd.F");
  spec.params["integration_method"] = std::string("invalid_method");

  SignalNamespace ns;
  GraphCompiler compiler;
  EXPECT_THROW(compiler.parse_model(spec, ns), std::runtime_error);
}

TEST(GraphCompilerTest, ParseDcMotorModel) {
  ModelSpec spec;
  spec.id = "motor";
  spec.type = "dc_motor";
  spec.params["resistance_ohm"] = 2.0;
  spec.params["inductance_h"] = 0.5;
  spec.params["torque_constant"] = 0.1;
  spec.params["back_emf_constant"] = 0.1;
  spec.params["inertia"] = 0.02;
  spec.params["viscous_friction"] = 0.2;
  spec.params["initial_current"] = 0.0;
  spec.params["initial_speed"] = 0.0;
  spec.params["speed_signal"] = std::string("motor.omega");
  spec.params["current_signal"] = std::string("motor.i");
  spec.params["torque_signal"] = std::string("motor.tau");
  spec.params["voltage_signal"] = std::string("motor.V");
  spec.params["load_torque_signal"] = std::string("motor.load");

  SignalNamespace ns;
  GraphCompiler compiler;
  std::unique_ptr<IModel> model(compiler.parse_model(spec, ns));

  ASSERT_NE(model, nullptr);
  EXPECT_NE(model->describe().find("DcMotor"), std::string::npos);
}

TEST(GraphCompilerTest, ParseDcMotorModelWithInvalidIntegrationMethodThrows) {
  ModelSpec spec;
  spec.id = "motor";
  spec.type = "dc_motor";
  spec.params["resistance_ohm"] = 2.0;
  spec.params["inductance_h"] = 0.5;
  spec.params["torque_constant"] = 0.1;
  spec.params["back_emf_constant"] = 0.1;
  spec.params["inertia"] = 0.02;
  spec.params["viscous_friction"] = 0.2;
  spec.params["initial_current"] = 0.0;
  spec.params["initial_speed"] = 0.0;
  spec.params["speed_signal"] = std::string("motor.omega");
  spec.params["current_signal"] = std::string("motor.i");
  spec.params["torque_signal"] = std::string("motor.tau");
  spec.params["voltage_signal"] = std::string("motor.V");
  spec.params["load_torque_signal"] = std::string("motor.load");
  spec.params["integration_method"] = std::string("invalid_method");

  SignalNamespace ns;
  GraphCompiler compiler;
  EXPECT_THROW(compiler.parse_model(spec, ns), std::runtime_error);
}

TEST(GraphCompilerTest, StrictModeRejectsUndeclaredModelSignalContracts) {
  GraphSpec spec;

  ModelSpec model;
  model.id = "pt1";
  model.type = "first_order_process";
  model.params["gain"] = 1.0;
  model.params["tau_s"] = 1.0;
  model.params["initial_output"] = 0.0;
  model.params["output_signal"] = std::string("pt1.y");
  model.params["input_signal"] = std::string("pt1.u");
  spec.models.push_back(model);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns, options),
               std::runtime_error);
}

TEST(GraphCompilerTest, StrictModeAllowsDeclaredModelSignalContracts) {
  GraphSpec spec;
  spec.signals.push_back({"pt1.u", "dimensionless"});
  spec.signals.push_back({"pt1.y", "dimensionless"});

  ModelSpec model;
  model.id = "pt1";
  model.type = "first_order_process";
  model.params["gain"] = 1.0;
  model.params["tau_s"] = 1.0;
  model.params["initial_output"] = 0.0;
  model.params["output_signal"] = std::string("pt1.y");
  model.params["input_signal"] = std::string("pt1.u");
  spec.models.push_back(model);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_NO_THROW(compiler.compile(spec, signal_ns, func_ns, options));
}

TEST(GraphCompilerTest, RegisterModelFactoryRejectsInvalidInputs) {
  GraphCompiler::ModelFactory empty_factory;

  EXPECT_THROW(
      GraphCompiler::register_model_factory(
          "",
          [](const ModelSpec &, SignalNamespace &) -> std::unique_ptr<IModel> {
            return nullptr;
          }),
      std::invalid_argument);
  EXPECT_THROW(GraphCompiler::register_model_factory("test.empty_model_factory",
                                                     empty_factory),
               std::invalid_argument);
}

TEST(GraphCompilerTest, RegisterModelFactorySupportsExternalTypes) {
  const std::string type = "test.constant_signal_model";
  if (!GraphCompiler::is_model_registered(type)) {
    GraphCompiler::register_model_factory(
        type,
        [](const ModelSpec &spec,
           SignalNamespace &ns) -> std::unique_ptr<IModel> {
          auto output_it = spec.params.find("output_signal");
          auto value_it = spec.params.find("value");
          auto unit_it = spec.params.find("unit");
          if (output_it == spec.params.end() || value_it == spec.params.end() ||
              unit_it == spec.params.end()) {
            throw std::runtime_error(
                "Missing required parameters for constant model");
          }

          const std::string output_path =
              variant_to_string(output_it->second, "model[test]/output_signal");
          const double value =
              variant_to_double(value_it->second, "model[test]/value");
          const std::string unit =
              variant_to_string(unit_it->second, "model[test]/unit");
          const SignalId output_id = ns.intern(output_path);

          return std::make_unique<ConstantSignalModel>(spec.id, output_id,
                                                       value, unit);
        });
  }

  ModelSpec spec;
  spec.id = "const_output";
  spec.type = type;
  spec.params["output_signal"] = std::string("custom.output");
  spec.params["value"] = 42.0;
  spec.params["unit"] = std::string("V");

  SignalNamespace ns;
  GraphCompiler compiler;
  std::unique_ptr<IModel> model(compiler.parse_model(spec, ns));
  ASSERT_NE(model, nullptr);

  SignalStore store;
  model->tick(0.1, store);

  const SignalId output_id = ns.resolve("custom.output");
  ASSERT_NE(output_id, INVALID_SIGNAL);
  EXPECT_DOUBLE_EQ(store.read_value(output_id), 42.0);
  EXPECT_EQ(store.read_unit(output_id), "V");
}

TEST(GraphCompilerTest, CompileGraphWithRegisteredCustomModel) {
  const std::string type = "test.constant_signal_model";
  if (!GraphCompiler::is_model_registered(type)) {
    GraphCompiler::register_model_factory(
        type,
        [](const ModelSpec &spec,
           SignalNamespace &ns) -> std::unique_ptr<IModel> {
          auto output_it = spec.params.find("output_signal");
          auto value_it = spec.params.find("value");
          auto unit_it = spec.params.find("unit");
          if (output_it == spec.params.end() || value_it == spec.params.end() ||
              unit_it == spec.params.end()) {
            throw std::runtime_error(
                "Missing required parameters for constant model");
          }

          const std::string output_path =
              variant_to_string(output_it->second, "model[test]/output_signal");
          const double value =
              variant_to_double(value_it->second, "model[test]/value");
          const std::string unit =
              variant_to_string(unit_it->second, "model[test]/unit");
          const SignalId output_id = ns.intern(output_path);

          return std::make_unique<ConstantSignalModel>(spec.id, output_id,
                                                       value, unit);
        });
  }

  GraphSpec spec;
  ModelSpec model_spec;
  model_spec.id = "const_model";
  model_spec.type = type;
  model_spec.params["output_signal"] = std::string("custom.compiled_output");
  model_spec.params["value"] = 7.0;
  model_spec.params["unit"] = std::string("A");
  spec.models.push_back(model_spec);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  auto program = compiler.compile(spec, signal_ns, func_ns);

  ASSERT_EQ(program.models.size(), 1u);

  SignalStore store;
  program.models[0]->tick(0.1, store);

  const SignalId output_id = signal_ns.resolve("custom.compiled_output");
  ASSERT_NE(output_id, INVALID_SIGNAL);
  EXPECT_DOUBLE_EQ(store.read_value(output_id), 7.0);
  EXPECT_EQ(store.read_unit(output_id), "A");
}

TEST(GraphCompilerTest, CustomModelOutputCollidesWithEdgeTarget) {
  const std::string type = "test.constant_signal_model";
  if (!GraphCompiler::is_model_registered(type)) {
    GraphCompiler::register_model_factory(
        type,
        [](const ModelSpec &spec,
           SignalNamespace &ns) -> std::unique_ptr<IModel> {
          auto output_it = spec.params.find("output_signal");
          auto value_it = spec.params.find("value");
          auto unit_it = spec.params.find("unit");
          if (output_it == spec.params.end() || value_it == spec.params.end() ||
              unit_it == spec.params.end()) {
            throw std::runtime_error(
                "Missing required parameters for constant model");
          }

          const std::string output_path =
              variant_to_string(output_it->second, "model[test]/output_signal");
          const double value =
              variant_to_double(value_it->second, "model[test]/value");
          const std::string unit =
              variant_to_string(unit_it->second, "model[test]/unit");
          const SignalId output_id = ns.intern(output_path);

          return std::make_unique<ConstantSignalModel>(spec.id, output_id,
                                                       value, unit);
        });
  }

  GraphSpec spec;

  ModelSpec model_spec;
  model_spec.id = "const_model";
  model_spec.type = type;
  model_spec.params["output_signal"] = std::string("collision.signal");
  model_spec.params["value"] = 7.0;
  model_spec.params["unit"] = std::string("A");
  spec.models.push_back(model_spec);

  EdgeSpec edge;
  edge.source_path = "input.signal";
  edge.target_path = "collision.signal";
  edge.transform.type = "linear";
  edge.transform.params["scale"] = 1.0;
  edge.transform.params["offset"] = 0.0;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns), std::runtime_error);
}

TEST(GraphCompilerTest, RegisterModelFactoryRejectsDuplicateType) {
  const std::string type = "test.duplicate_model";
  if (!GraphCompiler::is_model_registered(type)) {
    GraphCompiler::register_model_factory(
        type,
        [](const ModelSpec &, SignalNamespace &) -> std::unique_ptr<IModel> {
          return std::make_unique<ConstantSignalModel>("dup", INVALID_SIGNAL,
                                                       0.0, "dimensionless");
        });
  }

  EXPECT_THROW(
      GraphCompiler::register_model_factory(
          type,
          [](const ModelSpec &, SignalNamespace &) -> std::unique_ptr<IModel> {
            return std::make_unique<ConstantSignalModel>("dup2", INVALID_SIGNAL,
                                                         0.0, "dimensionless");
          }),
      std::runtime_error);
}

TEST(GraphCompilerTest, CustomModelWithInvalidOutputSignalIdThrows) {
  const std::string type = "test.invalid_output_model";
  if (!GraphCompiler::is_model_registered(type)) {
    GraphCompiler::register_model_factory(
        type,
        [](const ModelSpec &, SignalNamespace &) -> std::unique_ptr<IModel> {
          return std::make_unique<ConstantSignalModel>(
              "invalid", INVALID_SIGNAL, 1.0, "dimensionless");
        });
  }

  GraphSpec spec;
  ModelSpec model_spec;
  model_spec.id = "invalid_model";
  model_spec.type = type;
  spec.models.push_back(model_spec);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns), std::runtime_error);
}

TEST(GraphCompilerTest, RuleConditionEvaluation) {
  GraphSpec spec;

  RuleSpec rule;
  rule.id = "overtemp";
  rule.condition = "sensor.temp >= 50.0";
  ActionSpec action;
  action.device = "heater";
  action.function = "shutdown";
  action.args["code"] = int64_t{1};
  rule.actions.push_back(action);
  spec.rules.push_back(rule);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;

  CompiledProgram program = compiler.compile(spec, signal_ns, func_ns);
  ASSERT_EQ(program.rules.size(), 1);
  EXPECT_EQ(program.required_command_capacity, 1u);

  SignalId temp_id = signal_ns.resolve("sensor.temp");
  ASSERT_NE(temp_id, INVALID_SIGNAL);

  SignalStore store;
  store.write(temp_id, 49.9, "degC");
  EXPECT_FALSE(program.rules[0].condition(store));

  store.write(temp_id, 50.0, "degC");
  EXPECT_TRUE(program.rules[0].condition(store));
}

TEST(GraphCompilerTest, RequiredCommandCapacitySumsAllRuleActions) {
  GraphSpec spec;

  RuleSpec rule_a;
  rule_a.id = "r1";
  rule_a.condition = "sensor.a > 0.0";
  ActionSpec action_a1;
  action_a1.device = "controller";
  action_a1.function = "f1";
  rule_a.actions.push_back(action_a1);
  ActionSpec action_a2;
  action_a2.device = "controller";
  action_a2.function = "f2";
  rule_a.actions.push_back(action_a2);
  spec.rules.push_back(rule_a);

  RuleSpec rule_b;
  rule_b.id = "r2";
  rule_b.condition = "sensor.b > 0.0";
  ActionSpec action_b1;
  action_b1.device = "controller";
  action_b1.function = "f3";
  rule_b.actions.push_back(action_b1);
  spec.rules.push_back(rule_b);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;

  CompiledProgram program = compiler.compile(spec, signal_ns, func_ns);
  EXPECT_EQ(program.required_command_capacity, 3u);
}

TEST(GraphCompilerTest, InvalidRuleConditionThrows) {
  GraphSpec spec;
  RuleSpec rule;
  rule.id = "bad";
  rule.condition = "sensor.temp >< 50.0";
  spec.rules.push_back(rule);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;

  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns), std::runtime_error);
}

TEST(GraphCompilerTest, NumericCoercionIntToDouble) {
  TransformSpec spec;
  spec.type = "linear";
  spec.params["scale"] = int64_t{2};
  spec.params["offset"] = int64_t{3};

  GraphCompiler compiler;
  ITransform *tf = compiler.parse_transform(spec);
  ASSERT_NE(tf, nullptr);
  EXPECT_DOUBLE_EQ(tf->apply(10.0, 0.1), 23.0);
  delete tf;
}

TEST(GraphCompilerTest, NoiseSeedIsOptional) {
  TransformSpec spec;
  spec.type = "noise";
  spec.params["amplitude"] = 0.0;

  GraphCompiler compiler;
  ITransform *tf = compiler.parse_transform(spec);
  ASSERT_NE(tf, nullptr);
  EXPECT_DOUBLE_EQ(tf->apply(3.14, 0.1), 3.14);
  delete tf;
}

TEST(GraphCompilerTest, SaturationSupportsMinValueAliases) {
  TransformSpec spec;
  spec.type = "saturation";
  spec.params["min_value"] = -1.0;
  spec.params["max_value"] = 1.0;

  GraphCompiler compiler;
  ITransform *tf = compiler.parse_transform(spec);
  ASSERT_NE(tf, nullptr);
  EXPECT_DOUBLE_EQ(tf->apply(5.0, 0.1), 1.0);
  EXPECT_DOUBLE_EQ(tf->apply(-5.0, 0.1), -1.0);
  delete tf;
}

TEST(GraphCompilerTest, DelayBreaksFeedbackCycle) {
  GraphSpec spec;

  EdgeSpec edge1;
  edge1.source_path = "A";
  edge1.target_path = "B";
  edge1.transform.type = "linear";
  edge1.transform.params["scale"] = 1.0;
  edge1.transform.params["offset"] = 0.0;

  EdgeSpec edge2;
  edge2.source_path = "B";
  edge2.target_path = "A";
  edge2.transform.type = "delay";
  edge2.transform.params["delay_sec"] = 0.1;

  spec.edges.push_back(edge1);
  spec.edges.push_back(edge2);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;

  EXPECT_NO_THROW(compiler.compile(spec, signal_ns, func_ns));
}

TEST(GraphCompilerTest, StabilityValidationWithExpectedDt) {
  GraphSpec spec;

  ModelSpec model;
  model.id = "fast";
  model.type = "thermal_mass";
  model.params["temp_signal"] = std::string("fast.temp");
  model.params["power_signal"] = std::string("fast.power");
  model.params["ambient_signal"] = std::string("fast.ambient");
  model.params["thermal_mass"] = 1.0;
  model.params["heat_transfer_coeff"] = 100.0; // stability limit = 0.02
  model.params["initial_temp"] = 20.0;
  spec.models.push_back(model);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;

  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns, 0.1),
               std::runtime_error);
}

TEST(GraphCompilerTest, StrictModeRejectsUndeclaredEdgeContracts) {
  GraphSpec spec;
  EdgeSpec edge;
  edge.source_path = "sensor.temp";
  edge.target_path = "controller.temp";
  edge.transform.type = "linear";
  edge.transform.params["scale"] = 1.0;
  edge.transform.params["offset"] = 0.0;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns, options),
               std::runtime_error);
}

TEST(GraphCompilerTest, StrictModeRejectsLinearUnitBoundaryCrossing) {
  GraphSpec spec;
  spec.signals.push_back({"sensor.temp_c", "degC"});
  spec.signals.push_back({"sensor.temp_k", "K"});

  EdgeSpec edge;
  edge.source_path = "sensor.temp_c";
  edge.target_path = "sensor.temp_k";
  edge.transform.type = "linear";
  edge.transform.params["scale"] = 1.0;
  edge.transform.params["offset"] = 273.15;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns, options),
               std::runtime_error);
}

TEST(GraphCompilerTest, StrictModeAllowsUnitConvertWithDeclaredContracts) {
  GraphSpec spec;
  spec.signals.push_back({"sensor.temp_c", "degC"});
  spec.signals.push_back({"sensor.temp_k", "K"});

  EdgeSpec edge;
  edge.source_path = "sensor.temp_c";
  edge.target_path = "sensor.temp_k";
  edge.transform.type = "unit_convert";
  edge.transform.params["to_unit"] = std::string("K");
  edge.transform.params["from_unit"] = std::string("degC");
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_NO_THROW(compiler.compile(spec, signal_ns, func_ns, options));
}

TEST(GraphCompilerTest, StrictModeRejectsUnsignedCustomTransform) {
  const std::string type = "test.strict_unsigned_transform";
  if (!GraphCompiler::is_transform_registered(type)) {
    GraphCompiler::register_transform_factory(
        type, [](const TransformSpec &) -> std::unique_ptr<ITransform> {
          return std::make_unique<AffineTestTransform>(0.0);
        });
  }

  GraphSpec spec;
  spec.signals.push_back({"a", "dimensionless"});
  spec.signals.push_back({"b", "dimensionless"});

  EdgeSpec edge;
  edge.source_path = "a";
  edge.target_path = "b";
  edge.transform.type = type;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns, options),
               std::runtime_error);
}

TEST(GraphCompilerTest, StrictModeAllowsSignedCustomTransform) {
  const std::string type = "test.strict_signed_transform";
  if (!GraphCompiler::is_transform_registered(type)) {
    TransformSignature signature;
    signature.contract = TransformSignature::Contract::preserve;
    GraphCompiler::register_transform_factory_with_signature(
        type,
        [](const TransformSpec &) -> std::unique_ptr<ITransform> {
          return std::make_unique<AffineTestTransform>(0.0);
        },
        signature);
  }

  GraphSpec spec;
  spec.signals.push_back({"a", "dimensionless"});
  spec.signals.push_back({"b", "dimensionless"});

  EdgeSpec edge;
  edge.source_path = "a";
  edge.target_path = "b";
  edge.transform.type = type;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_NO_THROW(compiler.compile(spec, signal_ns, func_ns, options));
}

TEST(GraphCompilerTest, StrictModeRejectsUnsignedCustomModel) {
  const std::string type = "test.strict_unsigned_model";
  if (!GraphCompiler::is_model_registered(type)) {
    GraphCompiler::register_model_factory(
        type,
        [](const ModelSpec &, SignalNamespace &ns) -> std::unique_ptr<IModel> {
          const SignalId id = ns.intern("unsigned.model.output");
          return std::make_unique<ConstantSignalModel>("unsigned", id, 1.0,
                                                       "dimensionless");
        });
  }

  GraphSpec spec;
  spec.signals.push_back({"unsigned.model.output", "dimensionless"});
  ModelSpec model;
  model.id = "unsigned_model";
  model.type = type;
  spec.models.push_back(model);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns, options),
               std::runtime_error);
}

TEST(GraphCompilerTest, StrictModeAllowsSignedCustomModel) {
  const std::string type = "test.strict_signed_model";
  if (!GraphCompiler::is_model_registered(type)) {
    ModelSignature signature;
    signature.signal_param_units["output_signal"] = "dimensionless";
    GraphCompiler::register_model_factory_with_signature(
        type,
        [](const ModelSpec &model_spec,
           SignalNamespace &ns) -> std::unique_ptr<IModel> {
          const auto output_it = model_spec.params.find("output_signal");
          if (output_it == model_spec.params.end()) {
            throw std::runtime_error("Missing output_signal");
          }
          const SignalId output_id = ns.intern(
              variant_to_string(output_it->second, "model/output_signal"));
          return std::make_unique<ConstantSignalModel>(model_spec.id, output_id,
                                                       5.0, "dimensionless");
        },
        signature);
  }

  GraphSpec spec;
  spec.signals.push_back({"signed.model.output", "dimensionless"});
  ModelSpec model;
  model.id = "signed_model";
  model.type = type;
  model.params["output_signal"] = std::string("signed.model.output");
  spec.models.push_back(model);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_NO_THROW(compiler.compile(spec, signal_ns, func_ns, options));
}

TEST(GraphCompilerTest,
     StrictModeRejectsSignedCustomModelMissingRequiredScalarParameter) {
  const std::string type = "test.strict_scalar_required_model";
  if (!GraphCompiler::is_model_registered(type)) {
    ModelSignature signature;
    signature.signal_param_units["output_signal"] = "dimensionless";
    signature.scalar_param_signatures["gain"] = ScalarParamSignature{
        "dimensionless", ScalarConstraint::greater_than(0.0), true};
    GraphCompiler::register_model_factory_with_signature(
        type,
        [](const ModelSpec &model_spec,
           SignalNamespace &ns) -> std::unique_ptr<IModel> {
          const auto output_it = model_spec.params.find("output_signal");
          if (output_it == model_spec.params.end()) {
            throw std::runtime_error("Missing output_signal");
          }
          const SignalId output_id = ns.intern(
              variant_to_string(output_it->second, "model/output_signal"));
          return std::make_unique<ConstantSignalModel>(model_spec.id, output_id,
                                                       5.0, "dimensionless");
        },
        signature);
  }

  GraphSpec spec;
  spec.signals.push_back({"signed.scalar.output", "dimensionless"});
  ModelSpec model;
  model.id = "signed_scalar_missing";
  model.type = type;
  model.params["output_signal"] = std::string("signed.scalar.output");
  spec.models.push_back(model);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  try {
    auto program = compiler.compile(spec, signal_ns, func_ns, options);
    (void)program;
    FAIL() << "Expected strict-mode compile failure for missing scalar param";
  } catch (const std::runtime_error &e) {
    EXPECT_NE(std::string(e.what()).find("scalar parameter 'gain'"),
              std::string::npos);
  }
}

TEST(GraphCompilerTest,
     StrictModeRejectsSignedCustomModelScalarConstraintViolation) {
  const std::string type = "test.strict_scalar_violation_model";
  if (!GraphCompiler::is_model_registered(type)) {
    ModelSignature signature;
    signature.signal_param_units["output_signal"] = "dimensionless";
    signature.scalar_param_signatures["gain"] = ScalarParamSignature{
        "dimensionless", ScalarConstraint::greater_than(0.0), true};
    GraphCompiler::register_model_factory_with_signature(
        type,
        [](const ModelSpec &model_spec,
           SignalNamespace &ns) -> std::unique_ptr<IModel> {
          const auto output_it = model_spec.params.find("output_signal");
          if (output_it == model_spec.params.end()) {
            throw std::runtime_error("Missing output_signal");
          }
          const SignalId output_id = ns.intern(
              variant_to_string(output_it->second, "model/output_signal"));
          return std::make_unique<ConstantSignalModel>(model_spec.id, output_id,
                                                       5.0, "dimensionless");
        },
        signature);
  }

  GraphSpec spec;
  spec.signals.push_back({"signed.scalar.output", "dimensionless"});
  ModelSpec model;
  model.id = "signed_scalar_invalid";
  model.type = type;
  model.params["output_signal"] = std::string("signed.scalar.output");
  model.params["gain"] = 0.0;
  spec.models.push_back(model);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  try {
    auto program = compiler.compile(spec, signal_ns, func_ns, options);
    (void)program;
    FAIL() << "Expected strict-mode compile failure for scalar constraint";
  } catch (const std::runtime_error &e) {
    EXPECT_NE(std::string(e.what()).find("/gain"), std::string::npos);
  }
}

TEST(GraphCompilerTest,
     StrictModeAllowsSignedCustomModelWithValidScalarConstraint) {
  const std::string type = "test.strict_scalar_valid_model";
  if (!GraphCompiler::is_model_registered(type)) {
    ModelSignature signature;
    signature.signal_param_units["output_signal"] = "dimensionless";
    signature.scalar_param_signatures["gain"] = ScalarParamSignature{
        "dimensionless", ScalarConstraint::greater_than(0.0), true};
    GraphCompiler::register_model_factory_with_signature(
        type,
        [](const ModelSpec &model_spec,
           SignalNamespace &ns) -> std::unique_ptr<IModel> {
          const auto output_it = model_spec.params.find("output_signal");
          if (output_it == model_spec.params.end()) {
            throw std::runtime_error("Missing output_signal");
          }
          const SignalId output_id = ns.intern(
              variant_to_string(output_it->second, "model/output_signal"));
          return std::make_unique<ConstantSignalModel>(model_spec.id, output_id,
                                                       5.0, "dimensionless");
        },
        signature);
  }

  GraphSpec spec;
  spec.signals.push_back({"signed.scalar.output", "dimensionless"});
  ModelSpec model;
  model.id = "signed_scalar_valid";
  model.type = type;
  model.params["output_signal"] = std::string("signed.scalar.output");
  model.params["gain"] = 1.0;
  spec.models.push_back(model);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_NO_THROW(compiler.compile(spec, signal_ns, func_ns, options));
}

TEST(GraphCompilerTest, StrictModeRejectsRuleWithoutDeclaredLhsContract) {
  GraphSpec spec;
  RuleSpec rule;
  rule.id = "r";
  rule.condition = "undeclared.signal > 1.0";
  spec.rules.push_back(rule);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns, options),
               std::runtime_error);
}

TEST(GraphCompilerTest, StrictModeEnforcesThermalModelSignalContracts) {
  GraphSpec spec;
  spec.signals.push_back({"chamber.temp", "degC"});
  spec.signals.push_back({"chamber.power", "degC"});
  spec.signals.push_back({"ambient.temp", "degC"});

  ModelSpec model;
  model.id = "chamber";
  model.type = "thermal_mass";
  model.params["temp_signal"] = std::string("chamber.temp");
  model.params["power_signal"] = std::string("chamber.power");
  model.params["ambient_signal"] = std::string("ambient.temp");
  model.params["thermal_mass"] = 1000.0;
  model.params["heat_transfer_coeff"] = 10.0;
  model.params["initial_temp"] = 20.0;
  spec.models.push_back(model);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::strict;

  EXPECT_THROW(compiler.compile(spec, signal_ns, func_ns, options),
               std::runtime_error);
}

TEST(GraphCompilerTest, PermissiveModeEmitsLinearBoundaryWarning) {
  GraphSpec spec;
  spec.signals.push_back({"a", "degC"});
  spec.signals.push_back({"b", "W"});

  EdgeSpec edge;
  edge.source_path = "a";
  edge.target_path = "b";
  edge.transform.type = "linear";
  edge.transform.params["scale"] = 1.0;
  edge.transform.params["offset"] = 0.0;
  spec.edges.push_back(edge);

  std::vector<std::string> warnings;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::permissive;
  options.warning_handler = [&warnings](const std::string &message) {
    warnings.push_back(message);
  };

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  EXPECT_NO_THROW(compiler.compile(spec, signal_ns, func_ns, options));
  EXPECT_FALSE(warnings.empty());
}

TEST(GraphCompilerTest,
     PermissiveModeWarnsOnSignedCustomModelScalarConstraintViolation) {
  const std::string type = "test.permissive_scalar_warning_model";
  if (!GraphCompiler::is_model_registered(type)) {
    ModelSignature signature;
    signature.signal_param_units["output_signal"] = "dimensionless";
    signature.scalar_param_signatures["gain"] = ScalarParamSignature{
        "dimensionless", ScalarConstraint::greater_than(0.0), true};
    GraphCompiler::register_model_factory_with_signature(
        type,
        [](const ModelSpec &model_spec,
           SignalNamespace &ns) -> std::unique_ptr<IModel> {
          const auto output_it = model_spec.params.find("output_signal");
          if (output_it == model_spec.params.end()) {
            throw std::runtime_error("Missing output_signal");
          }
          const SignalId output_id = ns.intern(
              variant_to_string(output_it->second, "model/output_signal"));
          return std::make_unique<ConstantSignalModel>(model_spec.id, output_id,
                                                       5.0, "dimensionless");
        },
        signature);
  }

  GraphSpec spec;
  spec.signals.push_back({"permissive.scalar.output", "dimensionless"});
  ModelSpec model;
  model.id = "permissive_scalar_warning";
  model.type = type;
  model.params["output_signal"] = std::string("permissive.scalar.output");
  model.params["gain"] = 0.0;
  spec.models.push_back(model);

  std::vector<std::string> warnings;
  CompilationOptions options;
  options.dimensional_policy = DimensionalPolicy::permissive;
  options.warning_handler = [&warnings](const std::string &message) {
    warnings.push_back(message);
  };

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  EXPECT_NO_THROW(compiler.compile(spec, signal_ns, func_ns, options));

  bool saw_gain_warning = false;
  for (const auto &warning : warnings) {
    if (warning.find("/gain") != std::string::npos) {
      saw_gain_warning = true;
      break;
    }
  }
  EXPECT_TRUE(saw_gain_warning);
}

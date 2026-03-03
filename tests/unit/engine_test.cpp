#include "fluxgraph/engine.hpp"
#include <gtest/gtest.h>

using namespace fluxgraph;

TEST(EngineTest, LoadProgram) {
  Engine engine;
  EXPECT_FALSE(engine.is_loaded());

  CompiledProgram program;
  engine.load(std::move(program));

  EXPECT_TRUE(engine.is_loaded());
}

TEST(EngineTest, TickRequiresLoadedProgram) {
  Engine engine;
  SignalStore store;

  EXPECT_THROW(engine.tick(0.1, store), std::runtime_error);
}

TEST(EngineTest, TickRejectsNonPositiveDt) {
  Engine engine;
  SignalStore store;
  CompiledProgram program;
  engine.load(std::move(program));

  EXPECT_THROW(engine.tick(0.0, store), std::runtime_error);
  EXPECT_THROW(engine.tick(-0.1, store), std::runtime_error);
}

TEST(EngineTest, SimpleEdgeExecution) {
  GraphSpec spec;

  EdgeSpec edge;
  edge.source_path = "input";
  edge.target_path = "output";
  edge.transform.type = "linear";
  edge.transform.params["scale"] = 2.0;
  edge.transform.params["offset"] = 0.0;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;

  GraphCompiler compiler;
  CompiledProgram program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  // Set input
  SignalId input_id = signal_ns.resolve("input");
  SignalId output_id = signal_ns.resolve("output");
  store.write(input_id, 10.0, "dimensionless");

  // Tick
  engine.tick(0.1, store);

  // Check output
  double output = store.read_value(output_id);
  EXPECT_EQ(output, 20.0); // 2 * 10
}

TEST(EngineTest, EdgePropagationUsesTargetContractUnit) {
  GraphSpec spec;
  spec.signals.push_back({"input", "W"});
  spec.signals.push_back({"output", "degC"});

  EdgeSpec edge;
  edge.source_path = "input";
  edge.target_path = "output";
  edge.transform.type = "linear";
  edge.transform.params["scale"] = 1.0;
  edge.transform.params["offset"] = 0.0;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;
  GraphCompiler compiler;
  auto program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  SignalId input_id = signal_ns.resolve("input");
  SignalId output_id = signal_ns.resolve("output");
  store.write(input_id, 10.0, "W");

  engine.tick(0.1, store);

  EXPECT_DOUBLE_EQ(store.read_value(output_id), 10.0);
  EXPECT_EQ(store.read_unit(output_id), "degC");
}

TEST(EngineTest, TickPreallocatesSignalStoreFromProgramMetadata) {
  GraphSpec spec;

  EdgeSpec edge;
  edge.source_path = "input";
  edge.target_path = "output";
  edge.transform.type = "linear";
  edge.transform.params["scale"] = 1.0;
  edge.transform.params["offset"] = 0.0;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  GraphCompiler compiler;
  auto program = compiler.compile(spec, signal_ns, func_ns);

  SignalStore store;
  EXPECT_EQ(store.capacity(), 0u);

  Engine engine;
  engine.load(std::move(program));

  SignalId input_id = signal_ns.resolve("input");
  store.write(input_id, 1.0, "dimensionless");
  engine.tick(0.1, store);

  EXPECT_GE(store.capacity(), signal_ns.size());
}

TEST(EngineTest, DrainCommands) {
  Engine engine;
  CompiledProgram program;
  engine.load(std::move(program));

  auto commands = engine.drain_commands();
  EXPECT_TRUE(commands.empty());

  // Drain again should still be empty
  commands = engine.drain_commands();
  EXPECT_TRUE(commands.empty());
}

TEST(EngineTest, Reset) {
  GraphSpec spec;

  EdgeSpec edge;
  edge.source_path = "input";
  edge.target_path = "output";
  edge.transform.type = "first_order_lag";
  edge.transform.params["tau_s"] = 1.0;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;

  GraphCompiler compiler;
  CompiledProgram program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  SignalId input_id = signal_ns.resolve("input");
  SignalId output_id = signal_ns.resolve("output");

  // Run some ticks
  store.write(input_id, 100.0, "dimensionless");
  for (int i = 0; i < 10; ++i) {
    engine.tick(0.1, store);
  }

  double output_before_reset = store.read_value(output_id);

  // Reset
  engine.reset();

  // Tick again with different input
  store.write(input_id, 50.0, "dimensionless");
  engine.tick(0.1, store);

  double output_after_reset = store.read_value(output_id);

  // After reset, output should reinitialize to new input
  EXPECT_EQ(output_after_reset, 50.0);
}

TEST(EngineTest, ThermalMassIntegration) {
  GraphSpec spec;

  ModelSpec model_spec;
  model_spec.id = "thermal_test";
  model_spec.type = "thermal_mass";
  model_spec.params["thermal_mass"] = 1000.0;
  model_spec.params["heat_transfer_coeff"] = 10.0;
  model_spec.params["initial_temp"] = 25.0;
  model_spec.params["temp_signal"] = std::string("model/temperature");
  model_spec.params["power_signal"] = std::string("model/power");
  model_spec.params["ambient_signal"] = std::string("model/ambient");
  spec.models.push_back(model_spec);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;

  GraphCompiler compiler;
  CompiledProgram program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  // Set up inputs
  SignalId power_id = signal_ns.resolve("model/power");
  SignalId ambient_id = signal_ns.resolve("model/ambient");
  SignalId temp_id = signal_ns.resolve("model/temperature");

  store.write(power_id, 100.0, "W");
  store.write(ambient_id, 20.0, "degC");

  // Run simulation
  for (int i = 0; i < 10; ++i) {
    engine.tick(0.1, store);
  }

  double final_temp = store.read_value(temp_id);
  EXPECT_GT(final_temp, 25.0); // Should have heated up
}

TEST(EngineTest, RuntimeStabilityValidation) {
  GraphSpec spec;

  ModelSpec model_spec;
  model_spec.id = "unstable";
  model_spec.type = "thermal_mass";
  model_spec.params["thermal_mass"] = 1.0;
  model_spec.params["heat_transfer_coeff"] = 100.0; // limit = 0.02
  model_spec.params["initial_temp"] = 25.0;
  model_spec.params["temp_signal"] = std::string("unstable.temperature");
  model_spec.params["power_signal"] = std::string("unstable.power");
  model_spec.params["ambient_signal"] = std::string("unstable.ambient");
  spec.models.push_back(model_spec);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;

  GraphCompiler compiler;
  auto program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  SignalId power_id = signal_ns.resolve("unstable.power");
  SignalId ambient_id = signal_ns.resolve("unstable.ambient");
  store.write(power_id, 0.0, "W");
  store.write(ambient_id, 25.0, "degC");

  EXPECT_THROW(engine.tick(0.1, store), std::runtime_error);
}

TEST(EngineTest, EdgeChainPropagatesWithinSameTick) {
  GraphSpec spec;

  EdgeSpec edge_ab;
  edge_ab.source_path = "A";
  edge_ab.target_path = "B";
  edge_ab.transform.type = "linear";
  edge_ab.transform.params["scale"] = 2.0;
  edge_ab.transform.params["offset"] = 0.0;

  EdgeSpec edge_bc;
  edge_bc.source_path = "B";
  edge_bc.target_path = "C";
  edge_bc.transform.type = "linear";
  edge_bc.transform.params["scale"] = 1.0;
  edge_bc.transform.params["offset"] = 1.0;

  spec.edges.push_back(edge_ab);
  spec.edges.push_back(edge_bc);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;
  GraphCompiler compiler;
  auto program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  SignalId a_id = signal_ns.resolve("A");
  SignalId b_id = signal_ns.resolve("B");
  SignalId c_id = signal_ns.resolve("C");

  store.write(a_id, 5.0, "dimensionless");
  engine.tick(0.1, store);

  EXPECT_DOUBLE_EQ(store.read_value(b_id), 10.0);
  EXPECT_DOUBLE_EQ(store.read_value(c_id), 11.0);
}

TEST(EngineTest, ModelOutputVisibleToEdgesInSameTick) {
  GraphSpec spec;

  ModelSpec model_spec;
  model_spec.id = "thermal";
  model_spec.type = "thermal_mass";
  model_spec.params["thermal_mass"] = 1000.0;
  model_spec.params["heat_transfer_coeff"] = 10.0;
  model_spec.params["initial_temp"] = 25.0;
  model_spec.params["temp_signal"] = std::string("model.temperature");
  model_spec.params["power_signal"] = std::string("model.power");
  model_spec.params["ambient_signal"] = std::string("model.ambient");
  spec.models.push_back(model_spec);

  EdgeSpec edge;
  edge.source_path = "model.temperature";
  edge.target_path = "model.temperature_out";
  edge.transform.type = "linear";
  edge.transform.params["scale"] = 1.0;
  edge.transform.params["offset"] = 0.0;
  spec.edges.push_back(edge);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;
  GraphCompiler compiler;
  auto program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  SignalId power_id = signal_ns.resolve("model.power");
  SignalId ambient_id = signal_ns.resolve("model.ambient");
  SignalId temp_id = signal_ns.resolve("model.temperature");
  SignalId out_id = signal_ns.resolve("model.temperature_out");

  store.write(power_id, 0.0, "W");
  store.write(ambient_id, 25.0, "degC");

  engine.tick(0.1, store);

  EXPECT_DOUBLE_EQ(store.read_value(temp_id), 25.0);
  EXPECT_DOUBLE_EQ(store.read_value(out_id), 25.0);
}

TEST(EngineTest, RuleEvaluationEmitsCommands) {
  GraphSpec spec;

  RuleSpec rule;
  rule.id = "over_limit";
  rule.condition = "sensor.value > 10.0";

  ActionSpec action;
  action.device = "controller";
  action.function = "shutdown";
  action.args["reason"] = std::string("over_limit");
  rule.actions.push_back(action);
  spec.rules.push_back(rule);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;
  GraphCompiler compiler;
  auto program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  SignalId sensor_id = signal_ns.resolve("sensor.value");
  store.write(sensor_id, 15.0, "dimensionless");

  engine.tick(0.1, store);
  auto commands = engine.drain_commands();

  ASSERT_EQ(commands.size(), 1u);
  EXPECT_EQ(func_ns.lookup_device(commands[0].device), "controller");
  EXPECT_EQ(func_ns.lookup_function(commands[0].function), "shutdown");
}

TEST(EngineTest, RuleCommandsAccumulateUntilDrain) {
  GraphSpec spec;

  RuleSpec rule;
  rule.id = "emit_each_tick";
  rule.condition = "sensor.value >= 0.0";

  ActionSpec action;
  action.device = "controller";
  action.function = "noop";
  action.args["mode"] = std::string("hold");
  rule.actions.push_back(action);
  spec.rules.push_back(rule);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;
  GraphCompiler compiler;
  auto program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  SignalId sensor_id = signal_ns.resolve("sensor.value");
  store.write(sensor_id, 0.0, "dimensionless");

  engine.tick(0.1, store);
  engine.tick(0.1, store);

  auto commands = engine.drain_commands();
  ASSERT_EQ(commands.size(), 2u);
  EXPECT_EQ(func_ns.lookup_function(commands[0].function), "noop");
  EXPECT_EQ(func_ns.lookup_function(commands[1].function), "noop");
}

TEST(EngineTest, RuleCommandBacklogOverflowThrows) {
  GraphSpec spec;

  RuleSpec rule;
  rule.id = "emit_each_tick";
  rule.condition = "sensor.value >= 0.0";

  ActionSpec action;
  action.device = "controller";
  action.function = "noop";
  rule.actions.push_back(action);
  spec.rules.push_back(rule);

  SignalNamespace signal_ns;
  FunctionNamespace func_ns;
  SignalStore store;
  GraphCompiler compiler;
  auto program = compiler.compile(spec, signal_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  SignalId sensor_id = signal_ns.resolve("sensor.value");
  store.write(sensor_id, 0.0, "dimensionless");

  bool overflow_observed = false;
  for (int i = 0; i < 1000; ++i) {
    try {
      engine.tick(0.1, store);
    } catch (const std::runtime_error &e) {
      overflow_observed =
          std::string(e.what()).find("command backlog") != std::string::npos;
      break;
    }
  }

  EXPECT_TRUE(overflow_observed);
}

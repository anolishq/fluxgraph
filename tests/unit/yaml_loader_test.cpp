#ifdef FLUXGRAPH_YAML_ENABLED

#include "fluxgraph/loaders/yaml_loader.hpp"
#include <gtest/gtest.h>
#include <stdexcept>

using namespace fluxgraph::loaders;

TEST(YamlLoaderTest, LoadSimpleEdge) {
  std::string yaml = R"yaml(
edges:
  - source: input.value
    target: output.value
    transform:
      type: linear
      params:
        scale: 2.0
        offset: 1.0
)yaml";

  auto spec = load_yaml_string(yaml);

  ASSERT_EQ(spec.edges.size(), 1);
  EXPECT_EQ(spec.edges[0].source_path, "input.value");
  EXPECT_EQ(spec.edges[0].target_path, "output.value");
  EXPECT_EQ(spec.edges[0].transform.type, "linear");
  EXPECT_EQ(std::get<double>(spec.edges[0].transform.params["scale"]), 2.0);
  EXPECT_EQ(std::get<double>(spec.edges[0].transform.params["offset"]), 1.0);
}

TEST(YamlLoaderTest, LoadModel) {
  std::string yaml = R"yaml(
models:
  - id: chamber
    type: thermal_mass
    params:
      temp_signal: chamber.temp
      power_signal: chamber.power
      ambient_signal: ambient.temp
      thermal_mass: 1000.0
      heat_transfer_coeff: 10.0
      initial_temp: 25.0
)yaml";

  auto spec = load_yaml_string(yaml);

  ASSERT_EQ(spec.models.size(), 1);
  EXPECT_EQ(spec.models[0].id, "chamber");
  EXPECT_EQ(spec.models[0].type, "thermal_mass");
  EXPECT_EQ(std::get<std::string>(spec.models[0].params["temp_signal"]),
            "chamber.temp");
  EXPECT_EQ(std::get<double>(spec.models[0].params["thermal_mass"]), 1000.0);
}

TEST(YamlLoaderTest, LoadRule) {
  std::string yaml = R"yaml(
rules:
  - id: heater_on
    condition: chamber.temp < 20.0
    actions:
      - device: heater
        function: set_power
        args:
          power: 500.0
)yaml";

  auto spec = load_yaml_string(yaml);

  ASSERT_EQ(spec.rules.size(), 1);
  EXPECT_EQ(spec.rules[0].id, "heater_on");
  EXPECT_EQ(spec.rules[0].condition, "chamber.temp < 20.0");
  ASSERT_EQ(spec.rules[0].actions.size(), 1);
  EXPECT_EQ(spec.rules[0].actions[0].device, "heater");
  EXPECT_EQ(spec.rules[0].actions[0].function, "set_power");
  EXPECT_EQ(std::get<double>(spec.rules[0].actions[0].args["power"]), 500.0);
  EXPECT_EQ(spec.rules[0].on_error, "log_and_continue");
}

TEST(YamlLoaderTest, AllTransformTypes) {
  std::string yaml = R"yaml(
edges:
  - source: a
    target: b
    transform:
      type: linear
      params: {}
  - source: c
    target: d
    transform:
      type: first_order_lag
      params: {}
  - source: e
    target: f
    transform:
      type: delay
      params: {}
  - source: g
    target: h
    transform:
      type: noise
      params: {}
  - source: i
    target: j
    transform:
      type: saturation
      params: {}
  - source: k
    target: l
    transform:
      type: deadband
      params: {}
  - source: m
    target: n
    transform:
      type: rate_limiter
      params: {}
  - source: o
    target: p
    transform:
      type: moving_average
      params: {}
)yaml";

  auto spec = load_yaml_string(yaml);

  ASSERT_EQ(spec.edges.size(), 8);
  EXPECT_EQ(spec.edges[0].transform.type, "linear");
  EXPECT_EQ(spec.edges[1].transform.type, "first_order_lag");
  EXPECT_EQ(spec.edges[2].transform.type, "delay");
  EXPECT_EQ(spec.edges[3].transform.type, "noise");
  EXPECT_EQ(spec.edges[4].transform.type, "saturation");
  EXPECT_EQ(spec.edges[5].transform.type, "deadband");
  EXPECT_EQ(spec.edges[6].transform.type, "rate_limiter");
  EXPECT_EQ(spec.edges[7].transform.type, "moving_average");
}

TEST(YamlLoaderTest, MissingRequiredField) {
  std::string yaml = R"yaml(
edges:
  - source: input.value
    transform:
      type: linear
      params: {}
)yaml";

  EXPECT_THROW({ load_yaml_string(yaml); }, std::runtime_error);
}

TEST(YamlLoaderTest, InvalidTransformType) {
  std::string yaml = R"yaml(
edges:
  - source: input.value
    target: output.value
    transform:
      params: {}
)yaml";

  EXPECT_THROW({ load_yaml_string(yaml); }, std::runtime_error);
}

TEST(YamlLoaderTest, VariantTypes) {
  std::string yaml = R"yaml(
models:
  - id: test
    type: test_model
    params:
      double_val: 3.14
      int_val: 42
      bool_val: true
      string_val: hello
)yaml";

  auto spec = load_yaml_string(yaml);

  ASSERT_EQ(spec.models.size(), 1);
  EXPECT_EQ(std::get<double>(spec.models[0].params["double_val"]), 3.14);
  EXPECT_EQ(std::get<int64_t>(spec.models[0].params["int_val"]), 42);
  EXPECT_EQ(std::get<bool>(spec.models[0].params["bool_val"]), true);
  EXPECT_EQ(std::get<std::string>(spec.models[0].params["string_val"]),
            "hello");
}

TEST(YamlLoaderTest, NestedParamsSupported) {
  std::string yaml = R"yaml(
models:
  - id: nested
    type: test_model
    params:
      matrix:
        - [1, 2]
        - [3, 4]
      config:
        enabled: true
        label: demo
edges:
  - source: a
    target: b
    transform:
      type: linear
      params:
        coeff:
          scale: 2.0
          offset: 1.0
)yaml";

  auto spec = load_yaml_string(yaml);
  ASSERT_EQ(spec.models.size(), 1);
  ASSERT_EQ(spec.edges.size(), 1);

  const auto &matrix_value = spec.models[0].params.at("matrix");
  ASSERT_TRUE(std::holds_alternative<fluxgraph::ParamArray>(matrix_value));
  const auto &matrix = std::get<fluxgraph::ParamArray>(matrix_value);
  ASSERT_EQ(matrix.size(), 2u);
  ASSERT_TRUE(std::holds_alternative<fluxgraph::ParamArray>(matrix[0]));
  const auto &row0 = std::get<fluxgraph::ParamArray>(matrix[0]);
  ASSERT_EQ(row0.size(), 2u);
  EXPECT_EQ(std::get<int64_t>(row0[0]), 1);

  const auto &config_value = spec.models[0].params.at("config");
  ASSERT_TRUE(std::holds_alternative<fluxgraph::ParamObject>(config_value));
  const auto &config = std::get<fluxgraph::ParamObject>(config_value);
  EXPECT_TRUE(std::get<bool>(config.at("enabled")));
  EXPECT_EQ(std::get<std::string>(config.at("label")), "demo");

  const auto &coeff_value = spec.edges[0].transform.params.at("coeff");
  ASSERT_TRUE(std::holds_alternative<fluxgraph::ParamObject>(coeff_value));
}

TEST(YamlLoaderTest, RejectsNestedCommandArgs) {
  std::string yaml = R"yaml(
rules:
  - id: nested_args
    condition: a > 0
    actions:
      - device: dev
        function: fn
        args:
          payload:
            key: value
)yaml";

  EXPECT_THROW({ load_yaml_string(yaml); }, std::runtime_error);
}

TEST(YamlLoaderTest, RejectsNonMapParams) {
  std::string yaml = R"yaml(
models:
  - id: m
    type: test_model
    params: [1, 2, 3]
)yaml";

  EXPECT_THROW({ load_yaml_string(yaml); }, std::runtime_error);
}

TEST(YamlLoaderTest, EnforcesParamDepthLimit) {
  std::string yaml = "models:\\n  - id: m\\n    type: test_model\\n    params:\\n      x: ";
  for (int i = 0; i < 40; ++i) {
    yaml += "[";
  }
  yaml += "0";
  for (int i = 0; i < 40; ++i) {
    yaml += "]";
  }
  yaml += "\\n";

  EXPECT_THROW({ load_yaml_string(yaml); }, std::runtime_error);
}

TEST(YamlLoaderTest, EmptyGraph) {
  std::string yaml = "{}";

  auto spec = load_yaml_string(yaml);

  EXPECT_EQ(spec.signals.size(), 0);
  EXPECT_EQ(spec.edges.size(), 0);
  EXPECT_EQ(spec.models.size(), 0);
  EXPECT_EQ(spec.rules.size(), 0);
}

TEST(YamlLoaderTest, LoadSignalContracts) {
  std::string yaml = R"yaml(
signals:
  - path: chamber.temp
    unit: degC
  - path: heater.power
    unit: W
)yaml";

  auto spec = load_yaml_string(yaml);

  ASSERT_EQ(spec.signals.size(), 2);
  EXPECT_EQ(spec.signals[0].path, "chamber.temp");
  EXPECT_EQ(spec.signals[0].unit, "degC");
  EXPECT_EQ(spec.signals[1].path, "heater.power");
  EXPECT_EQ(spec.signals[1].unit, "W");
}

TEST(YamlLoaderTest, InvalidYaml) {
  std::string yaml = "{ invalid: yaml: syntax }";

  EXPECT_THROW({ load_yaml_string(yaml); }, std::runtime_error);
}

#endif // FLUXGRAPH_YAML_ENABLED

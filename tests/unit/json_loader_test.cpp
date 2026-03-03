#ifdef FLUXGRAPH_JSON_ENABLED

#include "fluxgraph/loaders/json_loader.hpp"
#include <gtest/gtest.h>
#include <stdexcept>

using namespace fluxgraph::loaders;

TEST(JsonLoaderTest, LoadSimpleEdge) {
  std::string json = R"({
        "edges": [
            {
                "source": "input.value",
                "target": "output.value",
                "transform": {
                    "type": "linear",
                    "params": {
                        "scale": 2.0,
                        "offset": 1.0
                    }
                }
            }
        ]
    })";

  auto spec = load_json_string(json);

  ASSERT_EQ(spec.edges.size(), 1);
  EXPECT_EQ(spec.edges[0].source_path, "input.value");
  EXPECT_EQ(spec.edges[0].target_path, "output.value");
  EXPECT_EQ(spec.edges[0].transform.type, "linear");
  EXPECT_EQ(std::get<double>(spec.edges[0].transform.params["scale"]), 2.0);
  EXPECT_EQ(std::get<double>(spec.edges[0].transform.params["offset"]), 1.0);
}

TEST(JsonLoaderTest, LoadModel) {
  std::string json = R"({
        "models": [
            {
                "id": "chamber",
                "type": "thermal_mass",
                "params": {
                    "temp_signal": "chamber.temp",
                    "power_signal": "chamber.power",
                    "ambient_signal": "ambient.temp",
                    "thermal_mass": 1000.0,
                    "heat_transfer_coeff": 10.0,
                    "initial_temp": 25.0
                }
            }
        ]
    })";

  auto spec = load_json_string(json);

  ASSERT_EQ(spec.models.size(), 1);
  EXPECT_EQ(spec.models[0].id, "chamber");
  EXPECT_EQ(spec.models[0].type, "thermal_mass");
  EXPECT_EQ(std::get<std::string>(spec.models[0].params["temp_signal"]),
            "chamber.temp");
  EXPECT_EQ(std::get<double>(spec.models[0].params["thermal_mass"]), 1000.0);
}

TEST(JsonLoaderTest, LoadRule) {
  std::string json = R"({
        "rules": [
            {
                "id": "heater_on",
                "condition": "chamber.temp < 20.0",
                "actions": [
                    {
                        "device": "heater",
                        "function": "set_power",
                        "args": {
                            "power": 500.0
                        }
                    }
                ]
            }
        ]
    })";

  auto spec = load_json_string(json);

  ASSERT_EQ(spec.rules.size(), 1);
  EXPECT_EQ(spec.rules[0].id, "heater_on");
  EXPECT_EQ(spec.rules[0].condition, "chamber.temp < 20.0");
  ASSERT_EQ(spec.rules[0].actions.size(), 1);
  EXPECT_EQ(spec.rules[0].actions[0].device, "heater");
  EXPECT_EQ(spec.rules[0].actions[0].function, "set_power");
  EXPECT_EQ(std::get<double>(spec.rules[0].actions[0].args["power"]), 500.0);
  EXPECT_EQ(spec.rules[0].on_error, "log_and_continue");
}

TEST(JsonLoaderTest, AllTransformTypes) {
  std::string json = R"({
        "edges": [
            {"source": "a", "target": "b", "transform": {"type": "linear", "params": {}}},
            {"source": "c", "target": "d", "transform": {"type": "first_order_lag", "params": {}}},
            {"source": "e", "target": "f", "transform": {"type": "delay", "params": {}}},
            {"source": "g", "target": "h", "transform": {"type": "noise", "params": {}}},
            {"source": "i", "target": "j", "transform": {"type": "saturation", "params": {}}},
            {"source": "k", "target": "l", "transform": {"type": "deadband", "params": {}}},
            {"source": "m", "target": "n", "transform": {"type": "rate_limiter", "params": {}}},
            {"source": "o", "target": "p", "transform": {"type": "moving_average", "params": {}}}
        ]
    })";

  auto spec = load_json_string(json);

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

TEST(JsonLoaderTest, MissingRequiredField) {
  std::string json = R"({
        "edges": [
            {
                "source": "input.value",
                "transform": {
                    "type": "linear",
                    "params": {}
                }
            }
        ]
    })";

  EXPECT_THROW({ load_json_string(json); }, std::runtime_error);
}

TEST(JsonLoaderTest, InvalidTransformType) {
  std::string json = R"({
        "edges": [
            {
                "source": "input.value",
                "target": "output.value",
                "transform": {
                    "params": {}
                }
            }
        ]
    })";

  EXPECT_THROW({ load_json_string(json); }, std::runtime_error);
}

TEST(JsonLoaderTest, VariantTypes) {
  std::string json = R"({
        "models": [
            {
                "id": "test",
                "type": "test_model",
                "params": {
                    "double_val": 3.14,
                    "int_val": 42,
                    "bool_val": true,
                    "string_val": "hello"
                }
            }
        ]
    })";

  auto spec = load_json_string(json);

  ASSERT_EQ(spec.models.size(), 1);
  EXPECT_EQ(std::get<double>(spec.models[0].params["double_val"]), 3.14);
  EXPECT_EQ(std::get<int64_t>(spec.models[0].params["int_val"]), 42);
  EXPECT_EQ(std::get<bool>(spec.models[0].params["bool_val"]), true);
  EXPECT_EQ(std::get<std::string>(spec.models[0].params["string_val"]),
            "hello");
}

TEST(JsonLoaderTest, EmptyGraph) {
  std::string json = "{}";

  auto spec = load_json_string(json);

  EXPECT_EQ(spec.signals.size(), 0);
  EXPECT_EQ(spec.edges.size(), 0);
  EXPECT_EQ(spec.models.size(), 0);
  EXPECT_EQ(spec.rules.size(), 0);
}

TEST(JsonLoaderTest, LoadSignalContracts) {
  std::string json = R"({
        "signals": [
            {"path": "chamber.temp", "unit": "degC"},
            {"path": "heater.power", "unit": "W"}
        ]
    })";

  auto spec = load_json_string(json);

  ASSERT_EQ(spec.signals.size(), 2);
  EXPECT_EQ(spec.signals[0].path, "chamber.temp");
  EXPECT_EQ(spec.signals[0].unit, "degC");
  EXPECT_EQ(spec.signals[1].path, "heater.power");
  EXPECT_EQ(spec.signals[1].unit, "W");
}

TEST(JsonLoaderTest, InvalidJson) {
  std::string json = "{ invalid json }";

  EXPECT_THROW({ load_json_string(json); }, std::runtime_error);
}

#endif // FLUXGRAPH_JSON_ENABLED

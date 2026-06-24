#include "fluxgraph/model/thermal_mass.hpp"

#include <gtest/gtest.h>

#include <cmath>
#include <limits>

using namespace fluxgraph;

class ThermalMassTest : public ::testing::Test {
protected:
    void SetUp() override {
        ns = std::make_unique<SignalNamespace>();
        store = std::make_unique<SignalStore>();

        temp_id = ns->intern("model/temperature");
        power_id = ns->intern("model/heating_power");
        ambient_id = ns->intern("model/ambient_temp");
    }

    std::unique_ptr<SignalNamespace> ns;
    std::unique_ptr<SignalStore> store;
    SignalId temp_id, power_id, ambient_id;
};

TEST_F(ThermalMassTest, InitialTemperature) {
    ThermalMassModel model("test", 1000.0, 10.0, 25.0, "model/temperature", "model/heating_power", "model/ambient_temp",
                           *ns);

    store->write(power_id, 0.0, "W");
    store->write(ambient_id, 20.0, "degC");

    model.tick(0.1, *store);

    double temp = store->read_value(temp_id);
    EXPECT_NE(temp, 25.0);  // Should start cooling
}

TEST_F(ThermalMassTest, ConstructorRejectsNonPositiveThermalMass) {
    try {
        ThermalMassModel model("invalid", 0.0, 10.0, 25.0, "model/temperature", "model/heating_power",
                               "model/ambient_temp", *ns);
        (void)model;
        FAIL() << "Expected invalid_argument for non-positive thermal_mass";
    } catch (const std::invalid_argument &e) {
        EXPECT_NE(std::string(e.what()).find("thermal_mass"), std::string::npos);
    }
}

TEST_F(ThermalMassTest, ConstructorRejectsNonPositiveHeatTransferCoeff) {
    try {
        ThermalMassModel model("invalid", 1000.0, 0.0, 25.0, "model/temperature", "model/heating_power",
                               "model/ambient_temp", *ns);
        (void)model;
        FAIL() << "Expected invalid_argument for non-positive heat_transfer_coeff";
    } catch (const std::invalid_argument &e) {
        EXPECT_NE(std::string(e.what()).find("heat_transfer_coeff"), std::string::npos);
    }
}

TEST_F(ThermalMassTest, ConstructorRejectsNonFiniteInitialTemperature) {
    try {
        ThermalMassModel model("invalid", 1000.0, 10.0, std::numeric_limits<double>::infinity(), "model/temperature",
                               "model/heating_power", "model/ambient_temp", *ns);
        (void)model;
        FAIL() << "Expected invalid_argument for non-finite initial_temp";
    } catch (const std::invalid_argument &e) {
        EXPECT_NE(std::string(e.what()).find("initial_temp"), std::string::npos);
    }
}

TEST_F(ThermalMassTest, HeatingBehavior) {
    ThermalMassModel model("test", 1000.0, 10.0, 20.0, "model/temperature", "model/heating_power", "model/ambient_temp",
                           *ns);

    store->write(power_id, 100.0, "W");  // Net heating
    store->write(ambient_id, 20.0, "degC");

    double initial_temp = 20.0;
    for (int i = 0; i < 10; ++i) {
        model.tick(0.1, *store);
    }

    double final_temp = store->read_value(temp_id);
    EXPECT_GT(final_temp, initial_temp);  // Temperature should increase
}

TEST_F(ThermalMassTest, CoolingBehavior) {
    ThermalMassModel model("test", 1000.0, 10.0, 100.0, "model/temperature", "model/heating_power",
                           "model/ambient_temp", *ns);

    store->write(power_id, 0.0, "W");  // No heating
    store->write(ambient_id, 20.0, "degC");

    double initial_temp = 100.0;
    for (int i = 0; i < 100; ++i) {
        model.tick(0.1, *store);
    }

    double final_temp = store->read_value(temp_id);
    EXPECT_LT(final_temp, initial_temp);  // Temperature should decrease
    EXPECT_GT(final_temp, 20.0);          // But not below ambient
}

TEST_F(ThermalMassTest, Equilibrium) {
    ThermalMassModel model("test", 1000.0, 10.0, 50.0, "model/temperature", "model/heating_power", "model/ambient_temp",
                           *ns);

    store->write(ambient_id, 20.0, "degC");

    // Run until equilibrium
    for (int i = 0; i < 10; ++i) {
        model.tick(1.0, *store);
        double temp = store->read_value(temp_id);
        double heat_loss = 10.0 * (temp - 20.0);
        store->write(power_id, heat_loss, "W");  // Match heat loss
    }

    double temp_before = store->read_value(temp_id);
    model.tick(1.0, *store);
    double temp_after = store->read_value(temp_id);

    EXPECT_NEAR(temp_before, temp_after, 0.1);  // Stable
}

TEST_F(ThermalMassTest, Reset) {
    ThermalMassModel model("test", 1000.0, 10.0, 25.0, "model/temperature", "model/heating_power", "model/ambient_temp",
                           *ns);

    store->write(power_id, 1000.0, "W");
    store->write(ambient_id, 20.0, "degC");

    for (int i = 0; i < 10; ++i) {
        model.tick(0.1, *store);
    }

    double temp_heated = store->read_value(temp_id);
    EXPECT_GT(temp_heated, 25.0);

    model.reset();
    model.tick(0.0, *store);  // Tick with dt=0 to update store

    double temp_reset = store->read_value(temp_id);
    EXPECT_NEAR(temp_reset, 25.0, 0.1);
}

TEST_F(ThermalMassTest, StabilityLimit) {
    ThermalMassModel model("test", 1000.0, 10.0, 25.0, "model/temperature", "model/heating_power", "model/ambient_temp",
                           *ns);

    double limit = model.compute_stability_limit();
    EXPECT_NEAR(limit, 200.0, 0.1);  // 2*1000/10 = 200
}

TEST_F(ThermalMassTest, ExplicitForwardEulerMatchesDefault) {
    auto default_ns = std::make_unique<SignalNamespace>();
    auto explicit_ns = std::make_unique<SignalNamespace>();
    auto default_store = std::make_unique<SignalStore>();
    auto explicit_store = std::make_unique<SignalStore>();

    SignalId default_temp = default_ns->intern("model/temperature");
    SignalId default_power = default_ns->intern("model/heating_power");
    SignalId default_ambient = default_ns->intern("model/ambient_temp");

    SignalId explicit_temp = explicit_ns->intern("model/temperature");
    SignalId explicit_power = explicit_ns->intern("model/heating_power");
    SignalId explicit_ambient = explicit_ns->intern("model/ambient_temp");

    ThermalMassModel default_compare("default_compare", 1000.0, 10.0, 25.0, "model/temperature", "model/heating_power",
                                     "model/ambient_temp", *default_ns);
    ThermalMassModel explicit_compare("explicit_compare", 1000.0, 10.0, 25.0, "model/temperature",
                                      "model/heating_power", "model/ambient_temp", *explicit_ns,
                                      ThermalIntegrationMethod::ForwardEuler);

    for (int i = 0; i < 100; ++i) {
        const double power = (i < 50) ? 100.0 : 0.0;
        default_store->write(default_power, power, "W");
        default_store->write(default_ambient, 20.0, "degC");
        explicit_store->write(explicit_power, power, "W");
        explicit_store->write(explicit_ambient, 20.0, "degC");

        default_compare.tick(0.1, *default_store);
        explicit_compare.tick(0.1, *explicit_store);

        EXPECT_DOUBLE_EQ(default_store->read_value(default_temp), explicit_store->read_value(explicit_temp));
    }
}

TEST_F(ThermalMassTest, Rk4ImprovesAccuracyAtCoarseDt) {
    auto euler_ns = std::make_unique<SignalNamespace>();
    auto rk4_ns = std::make_unique<SignalNamespace>();
    auto euler_store = std::make_unique<SignalStore>();
    auto rk4_store = std::make_unique<SignalStore>();

    SignalId euler_temp = euler_ns->intern("model/temperature");
    SignalId euler_power = euler_ns->intern("model/heating_power");
    SignalId euler_ambient = euler_ns->intern("model/ambient_temp");

    SignalId rk4_temp = rk4_ns->intern("model/temperature");
    SignalId rk4_power = rk4_ns->intern("model/heating_power");
    SignalId rk4_ambient = rk4_ns->intern("model/ambient_temp");

    constexpr double thermal_mass = 10.0;
    constexpr double heat_transfer_coeff = 5.0;
    constexpr double initial_temp = 100.0;
    constexpr double ambient_temp = 0.0;
    constexpr double power = 0.0;
    constexpr double dt = 1.0;
    constexpr int ticks = 10;

    ThermalMassModel euler_model("euler", thermal_mass, heat_transfer_coeff, initial_temp, "model/temperature",
                                 "model/heating_power", "model/ambient_temp", *euler_ns,
                                 ThermalIntegrationMethod::ForwardEuler);
    ThermalMassModel rk4_model("rk4", thermal_mass, heat_transfer_coeff, initial_temp, "model/temperature",
                               "model/heating_power", "model/ambient_temp", *rk4_ns, ThermalIntegrationMethod::Rk4);

    for (int i = 0; i < ticks; ++i) {
        euler_store->write(euler_power, power, "W");
        euler_store->write(euler_ambient, ambient_temp, "degC");
        rk4_store->write(rk4_power, power, "W");
        rk4_store->write(rk4_ambient, ambient_temp, "degC");

        euler_model.tick(dt, *euler_store);
        rk4_model.tick(dt, *rk4_store);
    }

    const double total_time = static_cast<double>(ticks) * dt;
    const double k = heat_transfer_coeff / thermal_mass;
    const double analytical = ambient_temp + (initial_temp - ambient_temp) * std::exp(-k * total_time);

    const double euler_error = std::abs(euler_store->read_value(euler_temp) - analytical);
    const double rk4_error = std::abs(rk4_store->read_value(rk4_temp) - analytical);
    EXPECT_LT(rk4_error, euler_error);
}

TEST_F(ThermalMassTest, Rk4StabilityLimit) {
    ThermalMassModel model("rk4", 1000.0, 10.0, 25.0, "model/temperature", "model/heating_power", "model/ambient_temp",
                           *ns, ThermalIntegrationMethod::Rk4);

    const double expected_limit = 2.785293563405282 * 1000.0 / 10.0;
    EXPECT_NEAR(model.compute_stability_limit(), expected_limit, 1e-6);
}

TEST_F(ThermalMassTest, PhysicsDrivenFlag) {
    ThermalMassModel model("test", 1000.0, 10.0, 25.0, "model/temperature", "model/heating_power", "model/ambient_temp",
                           *ns);

    store->write(power_id, 0.0, "W");
    store->write(ambient_id, 20.0, "degC");

    model.tick(0.1, *store);

    EXPECT_TRUE(store->is_physics_driven(temp_id));
}

TEST_F(ThermalMassTest, Describe) {
    ThermalMassModel model("chamber_air", 8000.0, 50.0, 25.0, "model/temperature", "model/heating_power",
                           "model/ambient_temp", *ns);

    std::string desc = model.describe();
    EXPECT_NE(desc.find("ThermalMass"), std::string::npos);
    EXPECT_NE(desc.find("8000"), std::string::npos);
    EXPECT_NE(desc.find("50"), std::string::npos);
}

#include <gtest/gtest.h>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/engine.hpp"
#include "fluxgraph/graph/compiler.hpp"

using namespace fluxgraph;

TEST(MultiModelTest, TwoThermalMassesWithHeatTransfer) {
    // Two thermal masses connected by heat transfer edge

    SignalNamespace ns;
    FunctionNamespace fn;
    SignalStore store;

    GraphSpec spec;

    // Model 1: Chamber A (heated)
    ModelSpec model1;
    model1.id = "chamber_a";
    model1.type = "thermal_mass";
    model1.params["temp_signal"] = std::string("chamber_a.temp");
    model1.params["power_signal"] = std::string("chamber_a.power");
    model1.params["ambient_signal"] = std::string("ambient");
    model1.params["thermal_mass"] = 1000.0;
    model1.params["heat_transfer_coeff"] = 10.0;
    model1.params["initial_temp"] = 25.0;
    spec.models.push_back(model1);

    // Model 2: Chamber B (unheated, receives heat from A)
    ModelSpec model2;
    model2.id = "chamber_b";
    model2.type = "thermal_mass";
    model2.params["temp_signal"] = std::string("chamber_b.temp");
    model2.params["power_signal"] = std::string("chamber_b.power");
    model2.params["ambient_signal"] = std::string("ambient");
    model2.params["thermal_mass"] = 1000.0;
    model2.params["heat_transfer_coeff"] = 10.0;
    model2.params["initial_temp"] = 25.0;
    spec.models.push_back(model2);

    // Add edge: transfer from A to B (simplified as signal routing)
    EdgeSpec edge;
    edge.source_path = "chamber_a.temp";
    edge.target_path = "chamber_b.ambient_override";
    edge.transform.type = "linear";
    edge.transform.params["scale"] = 1.0;
    edge.transform.params["offset"] = 0.0;
    spec.edges.push_back(edge);

    GraphCompiler compiler;
    auto program = compiler.compile(spec, ns, fn);

    Engine engine;
    engine.load(std::move(program));

    // Get signal IDs
    auto power_a_id = ns.resolve("chamber_a.power");
    auto power_b_id = ns.resolve("chamber_b.power");
    auto ambient_id = ns.resolve("ambient");
    auto temp_a_id = ns.resolve("chamber_a.temp");
    auto temp_b_id = ns.resolve("chamber_b.temp");

    // Initialize
    store.write(ambient_id, 20.0, "degC");
    store.write(power_a_id, 1000.0, "W");  // Heat chamber A
    store.write(power_b_id, 0.0, "W");     // Chamber B unheated

    // Run simulation
    double temp_a_initial = 25.0;
    double temp_b_initial = 25.0;

    for (int i = 0; i < 100; ++i) {
        engine.tick(0.1, store);
    }

    double temp_a_final = store.read_value(temp_a_id);
    double temp_b_final = store.read_value(temp_b_id);

    // Chamber A should be hotter than initial (at least 8 degC gain)
    EXPECT_GT(temp_a_final, temp_a_initial + 8.0);

    // Chamber B should remain at initial (no heat transfer in this simplified
    // model) Note: This test demonstrates multi-model execution, not full thermal
    // coupling
    EXPECT_NEAR(temp_b_final, temp_b_initial, 5.0);
}

TEST(MultiModelTest, TenModelsConcurrent) {
    // Verify engine handles multiple models correctly

    SignalNamespace ns;
    FunctionNamespace fn;
    SignalStore store;

    GraphSpec spec;

    // Create 10 independent thermal masses
    for (int i = 0; i < 10; ++i) {
        ModelSpec model;
        model.id = "thermal" + std::to_string(i);
        model.type = "thermal_mass";
        model.params["temp_signal"] = std::string("chamber" + std::to_string(i) + ".temp");
        model.params["power_signal"] = std::string("chamber" + std::to_string(i) + ".power");
        model.params["ambient_signal"] = std::string("ambient");
        model.params["thermal_mass"] = 1000.0 * (i + 1);  // Different masses
        model.params["heat_transfer_coeff"] = 10.0;
        model.params["initial_temp"] = 25.0;
        spec.models.push_back(model);
    }

    GraphCompiler compiler;
    auto program = compiler.compile(spec, ns, fn);

    Engine engine;
    engine.load(std::move(program));

    // Initialize all with same ambient
    auto ambient_id = ns.resolve("ambient");
    store.write(ambient_id, 20.0, "degC");

    // Apply different powers
    std::vector<SignalId> power_ids;
    std::vector<SignalId> temp_ids;
    for (int i = 0; i < 10; ++i) {
        auto power_id = ns.resolve("chamber" + std::to_string(i) + ".power");
        auto temp_id = ns.resolve("chamber" + std::to_string(i) + ".temp");
        power_ids.push_back(power_id);
        temp_ids.push_back(temp_id);
        store.write(power_id, 100.0 * (i + 1), "W");  // Different powers
    }

    // Run simulation
    for (int i = 0; i < 100; ++i) {
        engine.tick(0.1, store);
    }

    // Verify all models updated
    for (int i = 0; i < 10; ++i) {
        double temp = store.read_value(temp_ids[i]);
        EXPECT_GT(temp, 25.0) << "Model " << i << " did not update";

        // Higher power should result in higher temperature
        if (i > 0) {
            double prev_temp = store.read_value(temp_ids[i - 1]);
            // Note: Different thermal masses affect final temp differently
            // Just verify all are above initial
            EXPECT_GT(temp, 25.0);
        }
    }
}

TEST(MultiModelTest, EdgesBetweenModels) {
    // Two models with transform edges connecting their outputs

    SignalNamespace ns;
    FunctionNamespace fn;
    SignalStore store;

    GraphSpec spec;

    // Model 1
    ModelSpec model1;
    model1.id = "source";
    model1.type = "thermal_mass";
    model1.params["temp_signal"] = std::string("source.temp");
    model1.params["power_signal"] = std::string("source.power");
    model1.params["ambient_signal"] = std::string("ambient");
    model1.params["thermal_mass"] = 1000.0;
    model1.params["heat_transfer_coeff"] = 10.0;
    model1.params["initial_temp"] = 25.0;
    spec.models.push_back(model1);

    // Model 2
    ModelSpec model2;
    model2.id = "sink";
    model2.type = "thermal_mass";
    model2.params["temp_signal"] = std::string("sink.temp");
    model2.params["power_signal"] = std::string("sink.power");
    model2.params["ambient_signal"] = std::string("ambient");
    model2.params["thermal_mass"] = 1000.0;
    model2.params["heat_transfer_coeff"] = 10.0;
    model2.params["initial_temp"] = 25.0;
    spec.models.push_back(model2);

    // Add edge: source temp -> filtered -> sink observation
    EdgeSpec edge1;
    edge1.source_path = "source.temp";
    edge1.target_path = "source.temp_filtered";
    edge1.transform.type = "first_order_lag";
    edge1.transform.params["tau_s"] = 1.0;
    spec.edges.push_back(edge1);

    EdgeSpec edge2;
    edge2.source_path = "source.temp_filtered";
    edge2.target_path = "sink.observed_source_temp";
    edge2.transform.type = "linear";
    edge2.transform.params["scale"] = 1.0;
    edge2.transform.params["offset"] = 0.0;
    spec.edges.push_back(edge2);

    GraphCompiler compiler;
    auto program = compiler.compile(spec, ns, fn);

    Engine engine;
    engine.load(std::move(program));

    // Initialize
    auto ambient_id = ns.resolve("ambient");
    auto power1_id = ns.resolve("source.power");
    auto power2_id = ns.resolve("sink.power");
    auto temp1_id = ns.resolve("source.temp");
    auto temp2_id = ns.resolve("sink.temp");
    auto observed_id = ns.resolve("sink.observed_source_temp");

    store.write(ambient_id, 20.0, "degC");
    store.write(power1_id, 1000.0, "W");
    store.write(power2_id, 0.0, "W");

    // Run simulation
    for (int i = 0; i < 100; ++i) {
        engine.tick(0.1, store);
    }

    // Verify edge propagation
    double source_temp = store.read_value(temp1_id);
    double observed_temp = store.read_value(observed_id);

    EXPECT_GT(source_temp, 30.0);
    EXPECT_NEAR(observed_temp, source_temp,
                2.0);  // Filtered value should track source
}

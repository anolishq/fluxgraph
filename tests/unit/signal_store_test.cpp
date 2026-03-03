#include "fluxgraph/core/signal_store.hpp"
#include <gtest/gtest.h>

using namespace fluxgraph;

class SignalStoreTest : public ::testing::Test {
protected:
  SignalStore store;
};

TEST_F(SignalStoreTest, DefaultSignalIsZero) {
  Signal sig = store.read(0);
  EXPECT_EQ(sig.value, 0.0);
  EXPECT_EQ(sig.unit, "dimensionless");
}

TEST_F(SignalStoreTest, WriteAndReadValue) {
  store.write(1, 42.5);
  EXPECT_EQ(store.read_value(1), 42.5);
}

TEST_F(SignalStoreTest, WriteAndReadSignal) {
  store.write(1, 25.0, "degC");
  Signal sig = store.read(1);
  EXPECT_EQ(sig.value, 25.0);
  EXPECT_EQ(sig.unit, "degC");
  EXPECT_EQ(store.read_unit(1), "degC");
}

TEST_F(SignalStoreTest, InvalidSignalReturnsDefault) {
  Signal sig = store.read(INVALID_SIGNAL);
  EXPECT_EQ(sig.value, 0.0);
  EXPECT_EQ(sig.unit, "dimensionless");
  EXPECT_EQ(store.read_unit(INVALID_SIGNAL), "dimensionless");
}

TEST_F(SignalStoreTest, InvalidSignalWriteIsNoOp) {
  store.write(INVALID_SIGNAL, 100.0);
  EXPECT_EQ(store.size(), 0);
}

TEST_F(SignalStoreTest, PhysicsDrivenFlag) {
  SignalId id = 5;
  EXPECT_FALSE(store.is_physics_driven(id));

  store.mark_physics_driven(id, true);
  EXPECT_TRUE(store.is_physics_driven(id));

  store.mark_physics_driven(id, false);
  EXPECT_FALSE(store.is_physics_driven(id));
}

TEST_F(SignalStoreTest, DeclareUnitEnforcement) {
  SignalId id = 10;
  store.declare_unit(id, "V");

  // Writing with correct unit should succeed
  EXPECT_NO_THROW(store.write(id, 3.3, "V"));
  EXPECT_EQ(store.read_value(id), 3.3);

  // Writing with wrong unit should throw
  EXPECT_THROW(store.write(id, 5.0, "A"), std::runtime_error);
}

TEST_F(SignalStoreTest, ValidateUnit) {
  SignalId id = 15;
  store.declare_unit(id, "Pa");

  EXPECT_NO_THROW(store.validate_unit(id, "Pa"));
  EXPECT_THROW(store.validate_unit(id, "bar"), std::runtime_error);
}

TEST_F(SignalStoreTest, MultipleSignals) {
  store.write(1, 10.0, "V");
  store.write(2, 20.0, "A");
  store.write(3, 30.0, "W");

  EXPECT_EQ(store.size(), 3);
  EXPECT_EQ(store.read_value(1), 10.0);
  EXPECT_EQ(store.read_value(2), 20.0);
  EXPECT_EQ(store.read_value(3), 30.0);
}

TEST_F(SignalStoreTest, ReservePreallocatesSlotsWithoutChangingSize) {
  store.reserve(64);
  EXPECT_GE(store.capacity(), 64u);
  EXPECT_EQ(store.size(), 0u);
}

TEST_F(SignalStoreTest, SparseSignalIdsTrackLogicalSize) {
  store.write(100, 1.0, "V");
  EXPECT_EQ(store.size(), 1u);
  EXPECT_EQ(store.read_value(100), 1.0);
  EXPECT_EQ(store.read_value(99), 0.0);
  EXPECT_EQ(store.read_unit(99), "dimensionless");
}

TEST_F(SignalStoreTest, WriteWithSourceUnitPropagatesUnit) {
  store.write(1, 12.0, "degC");
  store.write_with_source_unit(2, 99.0, 1);

  EXPECT_EQ(store.read_value(2), 99.0);
  EXPECT_EQ(store.read_unit(2), "degC");
}

TEST_F(SignalStoreTest, WriteWithSourceUnitHandlesGrowthSafely) {
  store.write(1, 12.0, "degC");
  store.write_with_source_unit(1000, 55.0, 1);

  EXPECT_EQ(store.read_value(1000), 55.0);
  EXPECT_EQ(store.read_unit(1000), "degC");
}

TEST_F(SignalStoreTest, WriteWithSourceUnitFallsBackToDimensionless) {
  store.write_with_source_unit(8, 3.14, 999);
  EXPECT_EQ(store.read_value(8), 3.14);
  EXPECT_EQ(store.read_unit(8), "dimensionless");
}

TEST_F(SignalStoreTest, WriteWithContractUnitUsesDeclaredContract) {
  SignalId id = 50;
  store.declare_unit(id, "W");
  store.write_with_contract_unit(id, 123.0);

  EXPECT_EQ(store.read_value(id), 123.0);
  EXPECT_EQ(store.read_unit(id), "W");
}

TEST_F(SignalStoreTest, DeclareUnitRejectsConflictingRedefinition) {
  SignalId id = 51;
  store.declare_unit(id, "degC");
  EXPECT_THROW(store.declare_unit(id, "K"), std::runtime_error);
}

TEST_F(SignalStoreTest, OverwriteSignal) {
  store.write(1, 100.0, "degC");
  EXPECT_EQ(store.read_value(1), 100.0);

  store.write(1, 200.0, "degC");
  EXPECT_EQ(store.read_value(1), 200.0);
}

TEST_F(SignalStoreTest, FirstWriteDeclaresUnit) {
  SignalId id = 30;
  store.write(id, 1.0, "V");
  EXPECT_THROW(store.write(id, 2.0, "A"), std::runtime_error);
  EXPECT_NO_THROW(store.write(id, 2.0, "V"));
}

TEST_F(SignalStoreTest, EmptyUnitNormalizedToDimensionless) {
  SignalId id = 31;
  store.write(id, 1.0, "");
  auto sig = store.read(id);
  EXPECT_EQ(sig.unit, "dimensionless");
  EXPECT_NO_THROW(store.write(id, 2.0, "dimensionless"));
}

TEST_F(SignalStoreTest, DimensionlessDoesNotFreezeDeclaredUnit) {
  SignalId id = 32;
  store.write(id, 0.0, "dimensionless");
  EXPECT_NO_THROW(store.write(id, 1.0, "V"));
  EXPECT_THROW(store.write(id, 2.0, "A"), std::runtime_error);
}

TEST_F(SignalStoreTest, Clear) {
  store.write(1, 10.0);
  store.write(2, 20.0);
  store.mark_physics_driven(1, true);

  EXPECT_EQ(store.size(), 2);

  store.clear();

  EXPECT_EQ(store.size(), 0);
  EXPECT_FALSE(store.is_physics_driven(1));
}

TEST_F(SignalStoreTest, DeclaredUnitsPersistedAfterClear) {
  SignalId id = 20;
  store.declare_unit(id, "V");
  store.write(id, 5.0, "V");

  store.clear();

  // Declared unit should still be enforced
  EXPECT_THROW(store.write(id, 10.0, "A"), std::runtime_error);
  EXPECT_NO_THROW(store.write(id, 10.0, "V"));
}

#include <gtest/gtest.h>

#include "fluxgraph/core/units.hpp"

using namespace fluxgraph;

TEST(UnitRegistryTest, ContainsCuratedUnits) {
    const UnitRegistry &registry = UnitRegistry::instance();

    EXPECT_TRUE(registry.contains("dimensionless"));
    EXPECT_TRUE(registry.contains("rad"));
    EXPECT_TRUE(registry.contains("s"));
    EXPECT_TRUE(registry.contains("1/s"));
    EXPECT_TRUE(registry.contains("rad/s"));
    EXPECT_TRUE(registry.contains("m"));
    EXPECT_TRUE(registry.contains("m/s"));
    EXPECT_TRUE(registry.contains("kg"));
    EXPECT_TRUE(registry.contains("kg*m^2"));
    EXPECT_TRUE(registry.contains("N"));
    EXPECT_TRUE(registry.contains("N/m"));
    EXPECT_TRUE(registry.contains("N*s/m"));
    EXPECT_TRUE(registry.contains("N*m"));
    EXPECT_TRUE(registry.contains("N*m*s/rad"));
    EXPECT_TRUE(registry.contains("A"));
    EXPECT_TRUE(registry.contains("V"));
    EXPECT_TRUE(registry.contains("Ohm"));
    EXPECT_TRUE(registry.contains("H"));
    EXPECT_TRUE(registry.contains("N*m/A"));
    EXPECT_TRUE(registry.contains("V*s/rad"));
    EXPECT_TRUE(registry.contains("W"));
    EXPECT_TRUE(registry.contains("K"));
    EXPECT_TRUE(registry.contains("degC"));
    EXPECT_TRUE(registry.contains("delta_K"));
    EXPECT_TRUE(registry.contains("delta_degC"));
    EXPECT_TRUE(registry.contains("J/K"));
    EXPECT_TRUE(registry.contains("W/K"));
}

TEST(UnitRegistryTest, AbsoluteTemperatureAffineConversion) {
    const UnitRegistry &registry = UnitRegistry::instance();

    const UnitConversion c_to_k = registry.resolve_conversion("degC", "K");
    EXPECT_DOUBLE_EQ(c_to_k.scale, 1.0);
    EXPECT_DOUBLE_EQ(c_to_k.offset, 273.15);

    const UnitConversion c_to_c = registry.resolve_conversion("K", "degC");
    EXPECT_DOUBLE_EQ(c_to_c.scale, 1.0);
    EXPECT_DOUBLE_EQ(c_to_c.offset, -273.15);
}

TEST(UnitRegistryTest, DeltaTemperatureConversionIsNoOp) {
    const UnitRegistry &registry = UnitRegistry::instance();

    const UnitConversion c = registry.resolve_conversion("delta_degC", "delta_K");
    EXPECT_DOUBLE_EQ(c.scale, 1.0);
    EXPECT_DOUBLE_EQ(c.offset, 0.0);
}

TEST(UnitRegistryTest, RejectsAbsoluteDeltaBoundary) {
    const UnitRegistry &registry = UnitRegistry::instance();
    EXPECT_THROW(registry.resolve_conversion("degC", "delta_K"), std::runtime_error);
    EXPECT_THROW(registry.resolve_conversion("delta_K", "K"), std::runtime_error);
}

TEST(UnitRegistryTest, RejectsIncompatibleDimensions) {
    const UnitRegistry &registry = UnitRegistry::instance();
    EXPECT_THROW(registry.resolve_conversion("W", "degC"), std::runtime_error);
}

#include "fluxgraph/transform/unit_convert.hpp"
#include <gtest/gtest.h>
#include <memory>

using namespace fluxgraph;

TEST(UnitConvertTransformTest, AppliesAffineConversion) {
  UnitConvertTransform transform(1.0, 273.15);
  EXPECT_DOUBLE_EQ(transform.apply(25.0, 0.1), 298.15);
}

TEST(UnitConvertTransformTest, ClonePreservesCoefficients) {
  UnitConvertTransform transform(2.0, -5.0);
  std::unique_ptr<ITransform> clone(transform.clone());
  ASSERT_NE(clone, nullptr);
  EXPECT_DOUBLE_EQ(clone->apply(10.0, 0.0), 15.0);
}

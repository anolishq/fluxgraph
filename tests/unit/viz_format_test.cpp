#include "fluxgraph/viz/format.hpp"
#include <gtest/gtest.h>

namespace fluxgraph {
namespace {

TEST(VizFormat, ParsesKnownFormatsCaseInsensitive) {
  EXPECT_EQ(viz::parse_output_format("dot"), viz::OutputFormat::Dot);
  EXPECT_EQ(viz::parse_output_format("SVG"), viz::OutputFormat::Svg);
  EXPECT_EQ(viz::parse_output_format("Png"), viz::OutputFormat::Png);
}

TEST(VizFormat, RejectsUnknownFormat) {
  EXPECT_FALSE(viz::parse_output_format("jpeg").has_value());
  EXPECT_FALSE(viz::parse_output_format("").has_value());
}

TEST(VizFormat, ReturnsStableFormatNames) {
  EXPECT_STREQ(viz::output_format_name(viz::OutputFormat::Dot), "dot");
  EXPECT_STREQ(viz::output_format_name(viz::OutputFormat::Svg), "svg");
  EXPECT_STREQ(viz::output_format_name(viz::OutputFormat::Png), "png");
}

} // namespace
} // namespace fluxgraph


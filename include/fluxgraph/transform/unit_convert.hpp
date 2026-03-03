#pragma once

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Deterministic unit conversion transform (y = x * scale + offset).
class UnitConvertTransform : public ITransform {
public:
  UnitConvertTransform(double scale, double offset)
      : scale_(scale), offset_(offset) {}

  double apply(double input, double dt) override {
    (void)dt;
    return input * scale_ + offset_;
  }

  void reset() override {}

  ITransform *clone() const override {
    return new UnitConvertTransform(scale_, offset_);
  }

private:
  double scale_ = 1.0;
  double offset_ = 0.0;
};

} // namespace fluxgraph

#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>

#include "common.hpp"
#include "fluxgraph/transform/deadband.hpp"
#include "fluxgraph/transform/delay.hpp"
#include "fluxgraph/transform/first_order_lag.hpp"
#include "fluxgraph/transform/linear.hpp"
#include "fluxgraph/transform/moving_average.hpp"
#include "fluxgraph/transform/noise.hpp"
#include "fluxgraph/transform/rate_limiter.hpp"
#include "fluxgraph/transform/saturation.hpp"
#include "fluxgraph/transform/unit_convert.hpp"
#include "registry_builtins.hpp"

namespace fluxgraph::compiler_internal {

void register_builtin_transforms(FactoryRegistry &registry) {
    register_builtin_transform(
        registry, "linear",
        [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
            const std::string context = "transform[linear]";
            double scale = as_double(require_param(spec.params, "scale", context), context + "/scale");
            double offset = as_double(require_param(spec.params, "offset", context), context + "/offset");
            double clamp_min = -std::numeric_limits<double>::infinity();
            double clamp_max = std::numeric_limits<double>::infinity();

            if (auto it = spec.params.find("clamp_min"); it != spec.params.end()) {
                clamp_min = as_double(it->second, context + "/clamp_min");
            }
            if (auto it = spec.params.find("clamp_max"); it != spec.params.end()) {
                clamp_max = as_double(it->second, context + "/clamp_max");
            }

            return std::make_unique<LinearTransform>(scale, offset, clamp_min, clamp_max);
        },
        TransformSignature::Contract::linear_conditioning);

    register_builtin_transform(
        registry, "first_order_lag", [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
            const std::string context = "transform[first_order_lag]";
            double tau_s = as_double(require_param(spec.params, "tau_s", context), context + "/tau_s");
            return std::make_unique<FirstOrderLagTransform>(tau_s);
        });

    register_builtin_transform(registry, "delay", [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[delay]";
        double delay_sec = as_double(require_param(spec.params, "delay_sec", context), context + "/delay_sec");
        return std::make_unique<DelayTransform>(delay_sec);
    });

    register_builtin_transform(registry, "noise", [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[noise]";
        double amplitude = as_double(require_param(spec.params, "amplitude", context), context + "/amplitude");
        uint32_t seed = 0U;
        if (auto it = spec.params.find("seed"); it != spec.params.end()) {
            seed = static_cast<uint32_t>(as_int64(it->second, context + "/seed"));
        }
        return std::make_unique<NoiseTransform>(amplitude, seed);
    });

    register_builtin_transform(registry, "saturation", [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[saturation]";
        double min_val = 0.0;
        double max_val = 0.0;
        if (auto it = spec.params.find("min"); it != spec.params.end()) {
            min_val = as_double(it->second, context + "/min");
        } else {
            min_val = as_double(require_param(spec.params, "min_value", context), context + "/min_value");
        }

        if (auto it = spec.params.find("max"); it != spec.params.end()) {
            max_val = as_double(it->second, context + "/max");
        } else {
            max_val = as_double(require_param(spec.params, "max_value", context), context + "/max_value");
        }
        return std::make_unique<SaturationTransform>(min_val, max_val);
    });

    register_builtin_transform(registry, "deadband", [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[deadband]";
        double threshold = as_double(require_param(spec.params, "threshold", context), context + "/threshold");
        return std::make_unique<DeadbandTransform>(threshold);
    });

    register_builtin_transform(registry, "rate_limiter", [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[rate_limiter]";
        double max_rate = 0.0;
        if (auto it = spec.params.find("max_rate_per_sec"); it != spec.params.end()) {
            max_rate = as_double(it->second, context + "/max_rate_per_sec");
        } else {
            max_rate = as_double(require_param(spec.params, "max_rate", context), context + "/max_rate");
        }
        return std::make_unique<RateLimiterTransform>(max_rate);
    });

    register_builtin_transform(
        registry, "moving_average", [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
            const std::string context = "transform[moving_average]";
            int64_t window_size_raw =
                as_int64(require_param(spec.params, "window_size", context), context + "/window_size");
            if (window_size_raw <= 0) {
                throw std::runtime_error("Invalid parameter at " + context + "/window_size: expected >= 1");
            }
            size_t window_size = static_cast<size_t>(window_size_raw);
            return std::make_unique<MovingAverageTransform>(window_size);
        });

    register_builtin_transform(
        registry, "unit_convert",
        [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
            const std::string context = "transform[unit_convert]";
            double resolved_scale =
                as_double(require_param(spec.params, "__resolved_scale", context), context + "/__resolved_scale");
            double resolved_offset =
                as_double(require_param(spec.params, "__resolved_offset", context), context + "/__resolved_offset");
            return std::make_unique<UnitConvertTransform>(resolved_scale, resolved_offset);
        },
        TransformSignature::Contract::unit_convert);
}

}  // namespace fluxgraph::compiler_internal

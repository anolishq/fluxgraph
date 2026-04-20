# Transforms Reference

## Overview

Transforms process signal values in data flow chains. Each transform implements the ITransform interface:

```cpp
virtual double apply(double input, double dt) = 0;  // Process one sample
virtual void reset() = 0;                            // Reset internal state
virtual std::unique_ptr<ITransform> clone() const = 0;  // Deep copy
```

All transforms are **deterministic** - same inputs/dt always produce same output.

---

## 1. Linear Transform

**Type:** `linear`

**Function:** Affine transformation with optional clamping

**Formula:**

```
y = scale * x + offset
if clamp_min set: y = max(y, clamp_min)
if clamp_max set: y = min(y, clamp_max)
```

**Parameters:**

- `scale` (double, default=1.0) - Multiplicative factor
- `offset` (double, default=0.0) - Additive offset
- `clamp_min` (optional double) - Minimum output value
- `clamp_max` (optional double) - Maximum output value

**State:** Stateless (dt-independent)

**Use Cases:**

- Sensor calibration
- Range remapping
- Conditioning within a single unit contract

**Example:**

```cpp
EdgeSpec edge;
edge.source_path = "sensor.raw";
edge.target_path = "sensor.calibrated";
edge.transform.type = "linear";
edge.transform.params["scale"] = 2.5;
edge.transform.params["offset"] = -10.0;
edge.transform.params["clamp_min"] = 0.0;
edge.transform.params["clamp_max"] = 100.0;
```

---

## 1.5 Unit Convert Transform

**Type:** `unit_convert`

**Function:** Explicit cross-unit conversion using registry-derived coefficients.

**Parameters:**

- `to_unit` (string, required) - Target unit symbol
- `from_unit` (string, optional) - Source unit assertion

**State:** Stateless (dt-independent)

**Use Cases:**

- `degC` <-> `K` conversions
- Canonical unit normalization between subsystems
- Strict-mode replacement for implicit unit-boundary `linear` usage

---

## 2. First-Order Lag

**Type:** `first_order_lag`

**Function:** Low-pass filter (exponential smoothing)

**Formula:**

```
tau * dy/dt = x - y
Discrete: y_{n+1} = y_n + (dt/tau) * (x_n - y_n)
```

**Parameters:**

- `tau_s` (double, required) - Time constant in seconds
  - 63% response in tau seconds
  - 95% response in 3\*tau seconds
  - 99% response in 5\*tau seconds

**State:** Current filtered value y

**Behavior:**

- Larger tau = more smoothing, slower response
- tau=0 -> passthrough (no filtering)
- Output initializes to first input

**Use Cases:**

- Sensor noise filtering
- Smooth transitions/setpoints
- Simulate physical inertia

**Example:**

```cpp
EdgeSpec edge;
edge.source_path = "sensor.noisy";
edge.target_path = "sensor.filtered";
edge.transform.type = "first_order_lag";
edge.transform.params["tau_s"] = 2.0;  // 2-second time constant
```

**Frequency Response:**

- 3dB cutoff frequency: f*c = 1 / (2 * pi \_ tau)
- For tau=1.0: f_c ~= 0.16 Hz

**Analytical Validation:**
Step response matches exp(-t/tau) to within 0.001 error (see analytical tests).

---

## 3. Delay Transform

**Type:** `delay`

**Function:** Time-shift signal by fixed duration

**Formula:**

```
y(t) = x(t - delay_sec)
```

**Parameters:**

- `delay_sec` (double, required) - Delay duration in seconds

**State:** Circular buffer of past samples

**Behavior:**

- Output is input from delay_sec ago
- Buffer sized for delay_sec / dt samples
- Filled with 0.0 initially

**Use Cases:**

- Model transport delays (pipes, cables)
- Simulate processing latency
- Audio effects

**Example:**

```cpp
EdgeSpec edge;
edge.source_path = "source.signal";
edge.target_path = "delayed.signal";
edge.transform.type = "delay";
edge.transform.params["delay_sec"] = 0.5;  // 500ms delay
```

**Memory:** Approx delay_sec/dt \* 8 bytes (one double per buffered sample)

**Analytical Validation:**
Time shift exact to 1e-6 error for step, ramp, and sine inputs (see analytical tests).

---

## 4. Noise Transform

**Type:** `noise`

**Function:** Add Gaussian white noise

**Formula:**

```
y = x + N(0, amplitude)
where N is normal distribution
```

**Parameters:**

- `amplitude` (double, required) - Standard deviation of noise
- `seed` (optional uint32_t) - Random seed for repeatability

**State:** Random number generator state

**Behavior:**

- Deterministic if seed specified
- Different seeds give different noise sequences
- amplitude=0.0 -> passthrough

**Use Cases:**

- Simulate sensor noise
- Test robustness to disturbances
- Add realism to simulations

**Example:**

```cpp
EdgeSpec edge;
edge.source_path = "sensor.ideal";
edge.target_path = "sensor.noisy";
edge.transform.type = "noise";
edge.transform.params["amplitude"] = 0.5;  // +/- ~1.0 range (2*sigma)
edge.transform.params["seed"] = 42;        // Reproducible noise
```

**Statistical Properties:**

- Mean = input (unbiased)
- Std dev = amplitude
- 68% of samples within +/- amplitude
- 95% within +/- 2\*amplitude

---

## 5. Saturation Transform

**Type:** `saturation`

**Function:** Clamp signal to min/max bounds

**Formula:**

```
y = clamp(x, min_value, max_value)
  = max(min_value, min(max_value, x))
```

**Parameters:**

- `min_value` (double, required) - Minimum output
- `max_value` (double, required) - Maximum output

**State:** Stateless

**Behavior:**

- If x < min_value: y = min_value
- If x > max_value: y = max_value
- Otherwise: y = x

**Use Cases:**

- Enforce physical limits (0-100% valve)
- Prevent overdrive in controllers
- Model actuator saturation

**Example:**

```cpp
EdgeSpec edge;
edge.source_path = "controller.output";
edge.target_path = "actuator.command";
edge.transform.type = "saturation";
edge.transform.params["min_value"] = 0.0;
edge.transform.params["max_value"] = 100.0;
```

**Analytical Validation:**
Exact clamping (EXPECT_DOUBLE_EQ) with no overshoot (see analytical tests).

---

## 6. Deadband Transform

**Type:** `deadband`

**Function:** Zero output below threshold (noise gate)

**Formula:**

```
y = (|x| < threshold) ? 0.0 : x
```

**Parameters:**

- `threshold` (double, required) - Sensitivity threshold

**State:** Stateless

**Behavior:**

- Small signals suppressed
- Large signals pass through unchanged
- Applied to absolute value (symmetric)

**Use Cases:**

- Filter noise near zero
- Implement hysteresis
- Deadzone in joystick input

**Example:**

```cpp
EdgeSpec edge;
edge.source_path = "joystick.raw";
edge.target_path = "joystick.gated";
edge.transform.type = "deadband";
edge.transform.params["threshold"] = 0.05;  // Ignore small movements
```

**Analytical Validation:**
Exact threshold enforcement (EXPECT_DOUBLE_EQ) at boundary (see analytical tests).

---

## 7. Rate Limiter

**Type:** `rate_limiter`

**Function:** Limit how fast signal can change

**Formula:**

```
max_change = max_rate * dt
y_{n+1} = y_n + clamp(x_n - y_n, -max_change, max_change)
```

**Parameters:**

- `max_rate` (double, required) - Maximum rate of change (units/sec)

**State:** Current output value y

**Behavior:**

- Output changes by at most max_rate \* dt per tick
- Gradual approach to target
- Prevents sudden jumps

**Use Cases:**

- Smooth actuator commands (prevent jerking)
- Ramp setpoints gradually
- Model slew rate limits

**Example:**

```cpp
EdgeSpec edge;
edge.source_path = "setpoint.target";
edge.target_path = "setpoint.ramped";
edge.transform.type = "rate_limiter";
edge.transform.params["max_rate"] = 5.0;  // Max 5 units/sec change
```

**Time to settle (approx):**

```
t = |x_final - y_initial| / max_rate
```

**Analytical Validation:**
Slope constraint |dy/dt| <= max_rate verified (see analytical tests).

---

## 8. Moving Average

**Type:** `moving_average`

**Function:** Sliding window average (FIR filter)

**Formula:**

```
y_n = (1/N) * sum(x_{n-i}) for i=0 to N-1
where N = window_size
```

**Parameters:**

- `window_size` (int, required) - Number of samples to average

**State:** Circular buffer of past samples

**Behavior:**

- Averages last window_size samples
- Initial behavior: averages available samples (< window_size)
- window_size=1 -> passthrough

**Use Cases:**

- Reduce high-frequency noise
- Smooth jitter
- Cheap low-pass filter

**Example:**

```cpp
EdgeSpec edge;
edge.source_path = "sensor.jittery";
edge.target_path = "sensor.smoothed";
edge.transform.type = "moving_average";
edge.transform.params["window_size"] = 10;  // Average last 10 samples
```

**Memory:** window_size \* 8 bytes (double buffer)

**Frequency Response:**

- Acts as low-pass FIR filter
- Cutoff frequency: ~1/(window_size \* dt)

**Latency:** (window_size - 1) / 2 \* dt (group delay)

**Analytical Validation:**
Constant input gives exact average (EXPECT_DOUBLE_EQ), step response correct (see analytical tests).

---

## Transform Comparison

| Transform     | Stateful? | Memory      | Latency      | Use Case             |
| ------------- | --------- | ----------- | ------------ | -------------------- |
| Linear        | No        | 0           | 0            | Scaling, calibration |
| FirstOrderLag | Yes       | O(1)        | ~3\*tau      | Smooth filtering     |
| Delay         | Yes       | O(delay/dt) | delay_sec    | Transport lag        |
| Noise         | Yes       | O(1)        | 0            | Add disturbance      |
| Saturation    | No        | 0           | 0            | Enforce limits       |
| Deadband      | No        | 0           | 0            | Noise gate           |
| RateLimiter   | Yes       | O(1)        | Varies       | Slew rate limit      |
| MovingAverage | Yes       | O(window)   | window/2\*dt | Smooth jitter        |

---

## Chaining Transforms

Transforms can be chained by connecting target of one to source of another:

```cpp
// sensor.raw -> noise -> filter -> saturation -> output

EdgeSpec edge1;
edge1.source_path = "sensor.raw";
edge1.target_path = "sensor.noisy";
edge1.transform.type = "noise";
edge1.transform.params["amplitude"] = 1.0;

EdgeSpec edge2;
edge2.source_path = "sensor.noisy";
edge2.target_path = "sensor.filtered";
edge2.transform.type = "first_order_lag";
edge2.transform.params["tau_s"] = 0.5;

EdgeSpec edge3;
edge3.source_path = "sensor.filtered";
edge3.target_path = "sensor.output";
edge3.transform.type = "saturation";
edge3.transform.params["min_value"] = 0.0;
edge3.transform.params["max_value"] = 100.0;
```

**Execution order:** Graph compiler determines correct order via topological sort.

---

## Custom Transform Example

Implement ITransform for custom behavior:

```cpp
class HysteresisTransform : public fluxgraph::ITransform {
private:
    double m_on_threshold;
    double m_off_threshold;
    bool m_state = false;

public:
    HysteresisTransform(double on, double off)
        : m_on_threshold(on), m_off_threshold(off) {}

    double apply(double input, double dt) override {
        if (input > m_on_threshold) m_state = true;
        if (input < m_off_threshold) m_state = false;
        return m_state ? 1.0 : 0.0;
    }

    void reset() override {
        m_state = false;
    }

    std::unique_ptr<ITransform> clone() const override {
        return std::make_unique<HysteresisTransform>(*this);
    }
};
```

See [EMBEDDING.md](embedding.md) for registration details.

---

## Transform Best Practices

### 1. Choose dt Appropriately

For FirstOrderLag:

```
dt << tau (at least 10x smaller)
Example: tau=1.0s -> dt <= 0.1s
```

For Delay:

```text
dt should divide delay_sec evenly
Example: delay=0.5s -> dt=0.1s (5 samples) or 0.05s (10 samples)
```

### 2. Order Matters in Chains

```cpp
// Good: filter then limit
noise -> first_order_lag -> saturation

// Bad: limit then filter (spikes can still pass through limiter)
noise -> saturation -> first_order_lag
```

### 3. Reset State After Re-runs

```cpp
engine.reset();  // Resets all transform state
// Now ready for fresh simulation run
```

### 4. Avoid Excessive Buffering

```cpp
// Avoid: 10-second delay at 0.01s dt = 1000 samples = 8KB per edge
edge.transform.params["delay_sec"] = 10.0;  // High memory cost

// Better: Use FirstOrderLag if you just need smoothing
edge.transform.params["tau_s"] = 2.0;  // Minimal state, similar effect
```

### 5. Combine Transforms Efficiently

```cpp
// Inefficient: Two linear transforms
edge1: y = 2*x
edge2: z = y + 10

// Better: Single linear transform
edge: z = 2*x + 10
```

---

## Scientific Validation

All transforms validated against analytical solutions (see tests/analytical/):

- **FirstOrderLag:** Matches exp(-t/tau) to 0.001 error
- **ThermalMass:** Matches heat equation to 0.1 degC
- **Delay:** Exact time shift to 1e-6 error
- **Linear:** Exact (EXPECT_DOUBLE_EQ)
- **Saturation:** Exact clamping
- **Deadband:** Exact threshold
- **RateLimiter:** Slope constraint verified
- **MovingAverage:** Exact average for constant input

**Conclusion:** Numerically sound for real-world use.

---

## Performance Notes

**Relative costs (Debug build):**

- Linear: ~1ns
- Saturation/Deadband: ~2ns
- FirstOrderLag: ~5ns
- RateLimiter: ~5ns
- MovingAverage: ~10ns \* window_size
- Delay: ~3ns (circular buffer)
- Noise: ~20ns (RNG call)

**Release builds (-O3):** 2-5x faster

**Bottleneck:** Typically models (physics) dominate, not transforms.

---

## Future Enhancements

### Additional Transforms Under Consideration

- **PID Controller** - Proportional-Integral-Derivative control
- **LUT (Lookup Table)** - Piecewise linear interpolation
- **Integrator** - Accumulate signal over time
- **Differentiator** - Compute derivative (noisy, use carefully)
- **HighPassFilter** - Complement to FirstOrderLag
- **NotchFilter** - Reject specific frequency
- **Quantizer** - Round to discrete levels
- **Hysteresis** - Prevent chatter (see custom example above)

**To request:** Submit issue on GitHub with use case.

---

## Summary

FluxGraph provides 8 scientifically-validated transforms covering:

- Scaling (Linear)
- Filtering (FirstOrderLag, MovingAverage)
- Delays (Delay)
- Noise (Noise)
- Limiting (Saturation, Deadband, RateLimiter)

All transforms:

- Deterministic
- Validated analytically
- Efficient (sub-microsecond per call in Release)

**Next:** See [API.md](api-reference.md) for usage details, [EMBEDDING.md](embedding.md) for integration.

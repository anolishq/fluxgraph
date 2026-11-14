#include "model.hpp"

#include <array>
#include <cmath>
#include <format>

#include "exact_step.hpp"

namespace fluxgraph::v2::detail {

void Model::step(const double *x, const double *u, double *next) const {
    for (std::size_t i = 0; i < states; ++i) {
        double sum = 0.0;
        for (std::size_t j = 0; j < states; ++j) {
            sum += ad[i * states + j] * x[j];
        }
        for (std::size_t k = 0; k < inputs; ++k) {
            sum += bd[i * inputs + k] * u[k];
        }
        next[i] = sum;
    }
}

void Model::give(const double *x, const double *u, double *y) const {
    for (std::size_t i = 0; i < outputs; ++i) {
        double sum = 0.0;
        for (std::size_t j = 0; j < states; ++j) {
            sum += c[i * states + j] * x[j];
        }
        for (std::size_t k = 0; k < inputs; ++k) {
            if (direct[k]) {  // an input no output reads is not looked at, whatever it holds
                sum += d[i * inputs + k] * u[k];
            }
        }
        y[i] = sum;
    }
}

namespace {

using Kind = Setting::Kind;

constexpr double kStiffest = 100000.0;  // rule 7.8.7: the most a row of A, times the period, may come to

bool number_of(const Setting &setting, double &value) {
    if (setting.is(Kind::whole)) {
        value = static_cast<double>(setting.as_whole());
        return true;
    }
    if (setting.is(Kind::number) && std::isfinite(setting.as_number())) {
        value = setting.as_number();
        return true;
    }
    return false;
}

// A list of `count` finite numbers, appended to `values`. `count` of zero takes any length but none.
bool read_row(SettingsReader &settings, const Setting &row, std::string_view what, std::size_t count,
              std::vector<double> &values) {
    if (!row.is(Kind::list) || row.as_list().empty() || (count != 0 && row.as_list().size() != count)) {
        settings.fail(count != 0 ? std::format("{} has to be a list of {} numbers, and is {}", what, count,
                                               row.is(Kind::list) ? std::format("a list of {}", row.as_list().size())
                                                                  : std::string(row.kind_name()))
                                 : std::format("{} has to be a list of numbers, and not empty", what));
        return false;
    }
    for (const Setting &entry : row.as_list()) {
        double value = 0.0;
        if (!number_of(entry, value)) {
            settings.fail(std::format("{} holds {}, and every entry has to be a finite number", what, entry.shown()));
            return false;
        }
        values.push_back(value);
    }
    return true;
}

// A list of `rows` rows (any number, at least one, where `rows` is zero), each of `columns` numbers (likewise).
bool read_matrix(SettingsReader &settings, std::string_view key, std::size_t &rows, std::size_t &columns,
                 std::vector<double> &values) {
    const Setting *given = settings.raw(key);
    if (given == nullptr) {
        settings.fail(std::format("has no '{}' setting", key));
        return false;
    }
    if (!given->is(Kind::list) || given->as_list().empty() || (rows != 0 && given->as_list().size() != rows)) {
        settings.fail(rows != 0
                          ? std::format("setting '{}' has to be a list of {} rows, and is {}", key, rows,
                                        given->is(Kind::list) ? std::format("a list of {}", given->as_list().size())
                                                              : std::string(given->kind_name()))
                          : std::format("setting '{}' has to be a list of rows, and not empty", key));
        return false;
    }
    rows = given->as_list().size();
    for (std::size_t i = 0; i < rows; ++i) {
        if (!read_row(settings, given->as_list()[i], std::format("row {} of setting '{}'", i + 1, key), columns,
                      values)) {
            return false;
        }
        columns = given->as_list()[i].as_list().size();
    }
    return true;
}

// Names for the inputs, the states or the outputs of a `linear`: given, or `one` for a single one and `stem`
// with a number for several.
bool read_names(SettingsReader &settings, std::string_view key, std::size_t count, std::string_view one,
                std::string_view stem, std::vector<std::string> &names) {
    const Setting *given = settings.raw(key);
    if (given == nullptr) {
        for (std::size_t i = 0; i < count; ++i) {
            names.push_back(count == 1 ? std::string(one) : std::format("{}{}", stem, i));
        }
        return true;
    }
    if (!given->is(Kind::list) || given->as_list().size() != count) {
        settings.fail(std::format("setting '{}' has to be a list of {} names, one for each", key, count));
        return false;
    }
    for (const Setting &entry : given->as_list()) {
        // Rule 9.2: a name a block's settings give is not empty and holds no dot.
        if (!entry.is(Kind::text) || entry.as_text().empty() || entry.as_text().find('.') != std::string::npos) {
            settings.fail(std::format("setting '{}' holds {}, and a name is text, not empty and with no dot", key,
                                      entry.shown()));
            return false;
        }
        for (const std::string &other : names) {
            if (other == entry.as_text()) {
                settings.fail(std::format("setting '{}' holds the name '{}' twice", key, other));
                return false;
            }
        }
        names.push_back(entry.as_text());
    }
    return true;
}

void require(SettingsReader &settings, bool given, std::string_view key) {
    if (!given && !settings.failed()) {
        settings.fail(std::format("has no '{}' setting", key));
    }
}

// Works the step of a model in continuous time (rule 7.8.7), `b` being states by inputs, and refuses one that
// is too fast for the period or grows past what a double holds.
void finish_continuous(SettingsReader &settings, const std::vector<double> &b, Model &model) {
    model.continuous = true;
    const double fast = stiffness(model.a, model.states, settings.period());
    if (!(fast <= kStiffest)) {
        settings.fail(std::format(
            "the model is too stiff for the period: the largest sum along a row of its A, times the period, is {}, "
            "and may be {:.0f} at most (rule 7.8.7). Leave out a state far faster than the period, or rescale",
            fast, kStiffest));
        return;
    }
    exact_step(model.a, model.states, b, model.inputs, settings.period(), model.ad, model.bd);
    for (const std::vector<double> *matrix : {&model.ad, &model.bd}) {
        for (double entry : *matrix) {
            if (!std::isfinite(entry)) {
                settings.fail("the model grows so fast that its step over one period is more than a double holds");
                return;
            }
        }
    }
}

// Rule 7.8.6: three of the slowest time constant, rounded up to whole ticks, where `rate` is the largest real
// part among the eigenvalues of A and is below zero. Worked in doubles, and not exact.
void default_settle(SettingsReader &settings, double rate, Model &model) {
    if (!(rate < 0.0)) {
        return;  // a state that does not decay: no such constant
    }
    const double period_seconds = static_cast<double>(settings.period()) / 1e9;
    const double r = 3.0 * (-1.0 / rate) / period_seconds;
    const double ticks = std::ceil(r - 1e-9);  // the least whole number not less than r - 10^-9
    if (!(ticks < 18446744073709551616.0)) {
        settings.fail(
            "three of the model's slowest time constant is more ticks than this engine can count: write "
            "'settle'");
        return;
    }
    model.has_settle = true;
    model.settle = ticks > 0.0 ? static_cast<std::uint64_t>(ticks) : 0;
}

// The largest real part of the eigenvalues of a two by two A, from half its trace and its determinant, worked
// so that a slow rate beside a fast one is not lost in a subtraction (rule 7.8.6).
double slowest_of_two(double half_trace, double determinant) {
    if (half_trace * half_trace <= determinant) {
        return half_trace;
    }
    if (half_trace < 0.0) {
        return determinant / (half_trace - std::sqrt(half_trace * half_trace - determinant));
    }
    return 0.0;  // not reached with settings in their ranges: no constant
}

void set_names(Model &model, std::initializer_list<std::string_view> states,
               std::initializer_list<std::string_view> inputs) {
    model.state_names.assign(states.begin(), states.end());
    model.input_names.assign(inputs.begin(), inputs.end());
    model.states = states.size();
    model.inputs = inputs.size();
}

// The outputs of a named model are its states, each under its own name, unless it says otherwise.
void outputs_are_states(Model &model) {
    model.output_names = model.state_names;
    model.outputs = model.states;
    model.c.assign(model.states * model.states, 0.0);
    for (std::size_t i = 0; i < model.states; ++i) {
        model.c[i * model.states + i] = 1.0;
    }
}

void build_linear(SettingsReader &settings, Model &model) {
    std::size_t rows = 0;
    std::size_t columns = 0;
    std::vector<double> b;
    if (!read_matrix(settings, "A", rows, columns, model.a)) {
        return;
    }
    if (rows != columns) {
        settings.fail(std::format("setting 'A' has {} rows of {} numbers, and has to be square", rows, columns));
        return;
    }
    model.states = rows;
    if (!read_matrix(settings, "B", rows, model.inputs, b) ||
        !read_matrix(settings, "C", model.outputs, columns, model.c)) {
        return;
    }
    model.d.assign(model.outputs * model.inputs, 0.0);
    model.initial.assign(model.states, 0.0);
    if (!read_names(settings, "inputs", model.inputs, "u", "u", model.input_names) ||
        !read_names(settings, "states", model.states, "x0", "x", model.state_names) ||
        !read_names(settings, "outputs", model.outputs, "y", "y", model.output_names)) {
        return;
    }
    finish_continuous(settings, b, model);
}

void build_state_space(SettingsReader &settings, Model &model) {
    std::size_t rows = 0;
    std::size_t columns = 0;
    if (!read_matrix(settings, "A", rows, columns, model.ad)) {
        return;
    }
    if (rows != columns) {
        settings.fail(std::format("setting 'A' has {} rows of {} numbers, and has to be square", rows, columns));
        return;
    }
    model.states = rows;
    model.inputs = 1;
    model.outputs = 1;
    for (std::string_view key : {"B", "C"}) {
        const Setting *given = settings.raw(key);
        if (given == nullptr) {
            settings.fail(std::format("has no '{}' setting", key));
            return;
        }
        if (!read_row(settings, *given, std::format("setting '{}'", key), rows, key == "B" ? model.bd : model.c)) {
            return;
        }
    }
    model.d.assign(1, 0.0);
    settings.number("D", model.d[0]);
    model.initial.assign(rows, 0.0);
    for (std::size_t i = 0; i < rows; ++i) {
        model.state_names.push_back(std::format("x{}", i));
    }
    model.input_names = {"u"};
    model.output_names = {"y"};
}

}  // namespace

bool is_model_type(std::string_view type) {
    for (std::string_view known : {"linear", "thermal_mass", "thermal_rc2", "first_order_process",
                                   "second_order_process", "mass_spring_damper", "dc_motor", "state_space"}) {
        if (known == type) {
            return true;
        }
    }
    return false;
}

void build_model(std::string_view type, SettingsReader &settings, Model &model) {
    model = Model{};
    std::vector<double> b;
    bool named = true;
    double rate = 0.0;  // the largest real part among the eigenvalues of a named model's A
    if (type == "thermal_mass") {
        double mass = 1.0;
        double loss = 1.0;
        model.initial.assign(1, 0.0);
        require(settings, settings.positive("thermal_mass", mass), "thermal_mass");
        require(settings, settings.positive("heat_transfer", loss), "heat_transfer");
        require(settings, settings.number("initial", model.initial[0]), "initial");
        set_names(model, {"temp"}, {"power", "ambient"});
        // d temp/dt = (power - heat_transfer * (temp - ambient)) / thermal_mass
        model.a = {-loss / mass};
        b = {1.0 / mass, loss / mass};
        rate = model.a[0];
        outputs_are_states(model);
    } else if (type == "thermal_rc2") {
        double mass_a = 1.0;
        double mass_b = 1.0;
        double loss_a = 0.0;
        double loss_b = 0.0;
        double coupling = 0.0;
        model.initial.assign(2, 0.0);
        require(settings, settings.positive("thermal_mass_a", mass_a), "thermal_mass_a");
        require(settings, settings.positive("thermal_mass_b", mass_b), "thermal_mass_b");
        require(settings, settings.not_negative("heat_transfer_a", loss_a), "heat_transfer_a");
        require(settings, settings.not_negative("heat_transfer_b", loss_b), "heat_transfer_b");
        require(settings, settings.not_negative("coupling", coupling), "coupling");
        require(settings, settings.number("initial_a", model.initial[0]), "initial_a");
        require(settings, settings.number("initial_b", model.initial[1]), "initial_b");
        set_names(model, {"temp_a", "temp_b"}, {"power", "ambient"});
        model.a = {-(loss_a + coupling) / mass_a, coupling / mass_a, coupling / mass_b, -(loss_b + coupling) / mass_b};
        b = {1.0 / mass_a, loss_a / mass_a, 0.0, loss_b / mass_b};
        rate = slowest_of_two((model.a[0] + model.a[3]) / 2.0,
                              (loss_a * loss_b + coupling * (loss_a + loss_b)) / (mass_a * mass_b));
        outputs_are_states(model);
    } else if (type == "first_order_process") {
        double tau = 1.0;
        double gain = 1.0;
        model.initial.assign(1, 0.0);
        require(settings, settings.seconds("tau", tau), "tau");
        settings.number("gain", gain);
        settings.number("initial", model.initial[0]);
        set_names(model, {"y"}, {"u"});
        // dy/dt = (gain * u - y) / tau
        model.a = {-1.0 / tau};
        b = {gain / tau};
        rate = model.a[0];
        outputs_are_states(model);
    } else if (type == "second_order_process") {
        double omega = 1.0;
        double zeta = 0.0;
        double gain = 1.0;
        model.initial.assign(2, 0.0);
        require(settings, settings.positive("omega_n", omega), "omega_n");
        require(settings, settings.not_negative("zeta", zeta), "zeta");
        settings.number("gain", gain);
        settings.number("initial", model.initial[0]);
        settings.number("initial_rate", model.initial[1]);
        set_names(model, {"y", "rate"}, {"u"});
        // dy/dt = rate, and d rate/dt = omega_n^2 * (gain * u - y) - 2 * zeta * omega_n * rate
        model.a = {0.0, 1.0, -omega * omega, -2.0 * zeta * omega};
        b = {0.0, omega * omega * gain};
        rate = slowest_of_two((model.a[0] + model.a[3]) / 2.0, omega * omega);
        outputs_are_states(model);
    } else if (type == "mass_spring_damper") {
        double mass = 1.0;
        double damping = 0.0;
        double stiff = 0.0;
        model.initial.assign(2, 0.0);
        require(settings, settings.positive("mass", mass), "mass");
        require(settings, settings.not_negative("damping", damping), "damping");
        require(settings, settings.not_negative("stiffness", stiff), "stiffness");
        settings.number("initial_position", model.initial[0]);
        settings.number("initial_velocity", model.initial[1]);
        set_names(model, {"position", "velocity"}, {"force"});
        model.a = {0.0, 1.0, -stiff / mass, -damping / mass};
        b = {0.0, 1.0 / mass};
        rate = slowest_of_two((model.a[0] + model.a[3]) / 2.0, stiff / mass);
        outputs_are_states(model);
    } else if (type == "dc_motor") {
        double resistance = 0.0;
        double inductance = 1.0;
        double back_emf = 0.0;
        double torque = 0.0;
        double inertia = 1.0;
        double friction = 0.0;
        model.initial.assign(2, 0.0);
        require(settings, settings.not_negative("resistance", resistance), "resistance");
        require(settings, settings.positive("inductance", inductance), "inductance");
        require(settings, settings.not_negative("back_emf", back_emf), "back_emf");
        require(settings, settings.not_negative("torque_constant", torque), "torque_constant");
        require(settings, settings.positive("inertia", inertia), "inertia");
        require(settings, settings.not_negative("friction", friction), "friction");
        settings.number("initial_current", model.initial[0]);
        settings.number("initial_speed", model.initial[1]);
        set_names(model, {"current", "speed"}, {"voltage", "load_torque"});
        model.a = {-resistance / inductance, -back_emf / inductance, torque / inertia, -friction / inertia};
        b = {1.0 / inductance, 0.0, 0.0, -1.0 / inertia};
        rate = slowest_of_two((model.a[0] + model.a[3]) / 2.0,
                              (resistance * friction + back_emf * torque) / (inductance * inertia));
        // Outputs `speed`, `current`, and `torque`, which is torque_constant * current.
        model.output_names = {"speed", "current", "torque"};
        model.outputs = 3;
        model.c = {0.0, 1.0, 1.0, 0.0, torque, 0.0};
    } else if (type == "linear") {
        named = false;
        build_linear(settings, model);
    } else {
        named = false;
        build_state_space(settings, model);
    }
    if (settings.failed()) {
        return;
    }
    if (type == "linear") {
        // `D` and `initial`, whose sizes the other matrices give.
        if (settings.given("D")) {
            model.d.clear();
            std::size_t rows = model.outputs;
            std::size_t columns = model.inputs;
            if (!read_matrix(settings, "D", rows, columns, model.d)) {
                return;
            }
        }
        if (const Setting *initial = settings.raw("initial")) {
            model.initial.clear();
            if (!read_row(settings, *initial, "setting 'initial'", model.states, model.initial)) {
                return;
            }
        }
        for (const std::string &name : model.output_names) {
            if (name == "elapsed" || name == "doubtful" || name == "gaps") {
                settings.fail(std::format("an output is named '{}', which is a model output's name", name));
                return;
            }
        }
    } else if (type == "state_space") {
        if (const Setting *initial = settings.raw("initial")) {
            model.initial.clear();
            if (!read_row(settings, *initial, "setting 'initial'", model.states, model.initial)) {
                return;
            }
        }
    }
    if (named) {
        model.d.assign(model.outputs * model.inputs, 0.0);
        finish_continuous(settings, b, model);
        if (!settings.failed()) {
            default_settle(settings, rate, model);
        }
    }
    model.direct.assign(model.inputs, false);
    for (std::size_t k = 0; k < model.inputs; ++k) {
        for (std::size_t i = 0; i < model.outputs; ++i) {
            model.direct[k] = model.direct[k] || model.d[i * model.inputs + k] != 0.0;
        }
    }
}

}  // namespace fluxgraph::v2::detail

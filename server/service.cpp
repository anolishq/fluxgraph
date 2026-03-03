#include "service.hpp"

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <random>
#include <sstream>
#include <variant>

#include "fluxgraph/loaders/json_loader.hpp"
#include "fluxgraph/loaders/yaml_loader.hpp"

namespace fluxgraph::server {

// ============================================================================
// Constructor / Destructor
// ============================================================================

FluxGraphServiceImpl::FluxGraphServiceImpl(double dt) : dt_(dt) {
  std::cout << "[FluxGraph] Service initialized (dt=" << dt_ << "s)\n";
}

FluxGraphServiceImpl::~FluxGraphServiceImpl() {
  std::cout << "[FluxGraph] Service shutdown\n";
}

// ============================================================================
// LoadConfig RPC
// ============================================================================

grpc::Status
FluxGraphServiceImpl::LoadConfig(grpc::ServerContext * /*context*/,
                                 const fluxgraph::rpc::ConfigRequest *request,
                                 fluxgraph::rpc::ConfigResponse *response) {

  std::lock_guard lock(state_mutex_);

  try {
    // Check for no-op (matching hash)
    if (!request->config_hash().empty() &&
        request->config_hash() == current_config_hash_) {
      response->set_success(true);
      response->set_config_changed(false);
      std::cout << "[FluxGraph] LoadConfig: no-op (hash matched)\n";
      return grpc::Status::OK;
    }

    // Parse config based on format
    GraphSpec spec;
    if (request->format() == "yaml") {
#ifdef FLUXGRAPH_YAML_ENABLED
      spec = fluxgraph::loaders::load_yaml_string(request->config_content());
#else
      response->set_success(false);
      response->set_error_message(
          "YAML support not enabled (build with -DFLUXGRAPH_YAML_ENABLED=ON)");
      return grpc::Status(grpc::StatusCode::UNIMPLEMENTED,
                          "YAML support not enabled");
#endif
    } else if (request->format() == "json") {
#ifdef FLUXGRAPH_JSON_ENABLED
      spec = fluxgraph::loaders::load_json_string(request->config_content());
#else
      response->set_success(false);
      response->set_error_message(
          "JSON support not enabled (build with -DFLUXGRAPH_JSON_ENABLED=ON)");
      return grpc::Status(grpc::StatusCode::UNIMPLEMENTED,
                          "JSON support not enabled");
#endif
    } else {
      response->set_success(false);
      response->set_error_message("Unknown format: " + request->format() +
                                  " (must be 'yaml' or 'json')");
      return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT, "Unknown format");
    }

    // Clear existing namespaces (fresh start)
    signal_ns_.clear();
    func_ns_.clear();

    // Compile graph
    GraphCompiler compiler;
    auto program = compiler.compile(spec, signal_ns_, func_ns_, dt_);

    // Load into engine
    engine_.load(std::move(program));

    // Reset simulation state (fresh store to avoid stale declared-unit
    // carryover across config reloads).
    store_ = SignalStore();
    protected_write_signals_.clear();
    physics_owned_signals_.clear();
    sim_time_ = 0.0;
    tick_generation_ = 0;
    last_completed_generation_ = 0;
    last_completed_sim_time_ = 0.0;
    last_completed_commands_.clear();
    sessions_.clear();

    // Preload declared signal contracts so provider writes are validated
    // immediately (before first tick).
    for (const auto &signal_spec : spec.signals) {
      const SignalId signal_id = signal_ns_.resolve(signal_spec.path);
      if (signal_id != INVALID_SIGNAL) {
        store_.declare_unit(signal_id, signal_spec.unit);
      }
    }

    // Build write-authority map from spec.
    // - All edge targets are derived outputs and protected from external
    // writes.
    // - Model output signals are physics-owned and protected.
    for (const auto &edge : spec.edges) {
      const SignalId target_id = signal_ns_.resolve(edge.target_path);
      if (target_id != INVALID_SIGNAL) {
        protected_write_signals_.insert(target_id);
      }
    }

    for (const auto &model : spec.models) {
      if (model.type == "thermal_mass") {
        const auto temp_it = model.params.find("temp_signal");
        if (temp_it != model.params.end() &&
            std::holds_alternative<std::string>(temp_it->second)) {
          const auto &temp_path = std::get<std::string>(temp_it->second);
          const SignalId temp_id = signal_ns_.resolve(temp_path);
          if (temp_id != INVALID_SIGNAL) {
            protected_write_signals_.insert(temp_id);
            physics_owned_signals_.insert(temp_id);
            store_.mark_physics_driven(temp_id, true);
          }
        }
      }
    }

    // Update config hash
    current_config_hash_ = request->config_hash();
    loaded_ = true;

    response->set_success(true);
    response->set_config_changed(true);

    std::cout << "[FluxGraph] Config loaded: " << spec.models.size()
              << " models, " << spec.edges.size() << " edges, "
              << spec.rules.size() << " rules, dt=" << dt_ << "s\n";

    return grpc::Status::OK;

  } catch (const std::exception &e) {
    response->set_success(false);
    response->set_error_message(e.what());
    std::cerr << "[FluxGraph] LoadConfig failed: " << e.what() << "\n";
    return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT, e.what());
  }
}

// ============================================================================
// RegisterProvider RPC
// ============================================================================

grpc::Status FluxGraphServiceImpl::RegisterProvider(
    grpc::ServerContext * /*context*/,
    const fluxgraph::rpc::ProviderRegistration *request,
    fluxgraph::rpc::ProviderRegistrationResponse *response) {

  std::lock_guard lock(state_mutex_);

  if (!loaded_) {
    response->set_success(false);
    response->set_error_message("Config not loaded - call LoadConfig first");
    return grpc::Status(grpc::StatusCode::FAILED_PRECONDITION,
                        "Config not loaded");
  }

  if (request->provider_id().empty()) {
    response->set_success(false);
    response->set_error_message("provider_id must be non-empty");
    return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT,
                        "provider_id must be non-empty");
  }

  std::vector<std::string> requested_devices(request->device_ids().begin(),
                                             request->device_ids().end());

  const auto now = std::chrono::steady_clock::now();
  prune_stale_sessions_locked("", now);

  // Enforce unique provider identity and device ownership among active
  // sessions.
  for (const auto &[existing_session_id, existing_session] : sessions_) {
    if (existing_session.provider_id == request->provider_id()) {
      response->set_success(false);
      response->set_error_message("provider_id already registered: " +
                                  request->provider_id());
      return grpc::Status(grpc::StatusCode::ALREADY_EXISTS,
                          "provider_id already registered");
    }

    for (const auto &device_id : requested_devices) {
      const auto found =
          std::find(existing_session.device_ids.begin(),
                    existing_session.device_ids.end(), device_id);
      if (found != existing_session.device_ids.end()) {
        response->set_success(false);
        response->set_error_message(
            "device_id already owned by another provider: " + device_id);
        return grpc::Status(grpc::StatusCode::ALREADY_EXISTS,
                            "device_id ownership conflict");
      }
    }
  }

  // Generate unique session ID
  std::string session_id = generate_session_id(request->provider_id());

  // Store provider session
  ProviderSession session;
  session.provider_id = request->provider_id();
  session.device_ids = std::move(requested_devices);
  session.last_update = now;
  session.last_tick_generation =
      std::nullopt; // Must submit updates for generation 0

  sessions_[session_id] = std::move(session);

  response->set_success(true);
  response->set_session_id(session_id);

  std::cout << "[FluxGraph] Provider registered: " << request->provider_id()
            << " (session: " << session_id << ")\n";

  return grpc::Status::OK;
}

grpc::Status FluxGraphServiceImpl::UnregisterProvider(
    grpc::ServerContext * /*context*/,
    const fluxgraph::rpc::UnregisterRequest *request,
    fluxgraph::rpc::UnregisterResponse *response) {
  std::unique_lock<std::mutex> lock(state_mutex_);

  if (request->session_id().empty()) {
    response->set_success(false);
    response->set_error_message("session_id must be non-empty");
    return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT,
                        "session_id must be non-empty");
  }

  const auto session_it = sessions_.find(request->session_id());
  if (session_it == sessions_.end()) {
    response->set_success(false);
    response->set_error_message("Unknown session_id");
    return grpc::Status(grpc::StatusCode::UNAUTHENTICATED,
                        "Unknown session_id");
  }

  const std::string provider_id = session_it->second.provider_id;
  sessions_.erase(session_it);

  response->set_success(true);
  std::cout << "[FluxGraph] Provider unregistered: " << provider_id
            << " (session: " << request->session_id() << ")\n";

  lock.unlock();
  tick_cv_.notify_all();
  return grpc::Status::OK;
}

// ============================================================================
// UpdateSignals RPC (Server-Driven Tick)
// ============================================================================

grpc::Status FluxGraphServiceImpl::UpdateSignals(
    grpc::ServerContext * /*context*/,
    const fluxgraph::rpc::SignalUpdates *request,
    fluxgraph::rpc::TickResponse *response) {

  std::unique_lock<std::mutex> lock(state_mutex_);

  if (!loaded_) {
    return grpc::Status(grpc::StatusCode::FAILED_PRECONDITION,
                        "Config not loaded");
  }

  // Validate session
  auto session_it = sessions_.find(request->session_id());
  if (session_it == sessions_.end()) {
    return grpc::Status(grpc::StatusCode::UNAUTHENTICATED,
                        "Invalid session_id - call RegisterProvider first");
  }

  const auto now = std::chrono::steady_clock::now();
  session_it->second.last_update = now;
  prune_stale_sessions_locked(request->session_id(), now);

  const uint64_t current_generation = tick_generation_;

  // Write signals from provider to store
  for (const auto &sig : request->signals()) {
    SignalId id = signal_ns_.resolve(sig.path());
    if (id == INVALID_SIGNAL) {
      return grpc::Status(grpc::StatusCode::INVALID_ARGUMENT,
                          "Unknown signal: " + sig.path());
    }
    if (protected_write_signals_.count(id) > 0) {
      return grpc::Status(grpc::StatusCode::PERMISSION_DENIED,
                          "Write denied for protected signal: " + sig.path());
    }
    store_.write(id, sig.value(), sig.unit().c_str());
  }

  // Mark this provider as updated for CURRENT generation
  session_it->second.last_tick_generation = current_generation;

  // Check if ALL active providers have updated for this generation
  bool all_ready = !sessions_.empty();
  for (const auto &[session_id, session] : sessions_) {
    if (!session.last_tick_generation.has_value() ||
        session.last_tick_generation.value() < current_generation) {
      all_ready = false;
      break;
    }
  }

  if (all_ready) {
    // Last provider to arrive: execute one physics tick.
    engine_.tick(dt_, store_);
    sim_time_ += dt_;

    // Advance generation for next tick.
    tick_generation_++;

    // Drain command queue exactly once for this completed tick.
    last_completed_generation_ = tick_generation_;
    last_completed_sim_time_ = sim_time_;
    last_completed_commands_ = engine_.drain_commands();

    // Build response for this session from shared completed-tick snapshot.
    populate_tick_response_for_session_locked(request->session_id(), response);

    // Log major tick milestones only (reduces output spam)
    static int last_logged_tick = -1;
    int current_tick = static_cast<int>(sim_time_ / dt_);
    if (current_tick == 0 ||
        (current_tick % 100 == 0 && current_tick != last_logged_tick) ||
        (current_tick < 10)) {
      std::cout << "[FluxGraph] Tick " << current_tick << " (t=" << std::fixed
                << std::setprecision(1) << sim_time_
                << "s, generation=" << tick_generation_
                << ", commands=" << response->commands_size() << ")\n";
      last_logged_tick = current_tick;
    }

    lock.unlock();
    tick_cv_.notify_all();

  } else {
    // Early provider: wait until current generation completes.
    const std::string provider_id = session_it->second.provider_id;
    const auto wait_start = std::chrono::steady_clock::now();
    bool ticked = tick_cv_.wait_for(
        lock, std::chrono::milliseconds(2000), [this, current_generation]() {
          return tick_generation_ > current_generation;
        });

    const auto wait_duration =
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - wait_start)
            .count();

    if (ticked) {
      populate_tick_response_for_session_locked(request->session_id(),
                                                response);
    } else {
      std::cerr << "[FluxGraph] WARNING: " << provider_id
                << " timed out waiting for tick (generation="
                << current_generation << ", waited " << wait_duration
                << "ms)\n";
      response->set_tick_occurred(false);
      response->set_sim_time_sec(sim_time_);
    }
  }

  return grpc::Status::OK;
}

// ============================================================================
// ReadSignals RPC
// ============================================================================

grpc::Status
FluxGraphServiceImpl::ReadSignals(grpc::ServerContext * /*context*/,
                                  const fluxgraph::rpc::SignalRequest *request,
                                  fluxgraph::rpc::SignalResponse *response) {

  std::lock_guard lock(state_mutex_);

  if (!loaded_) {
    return grpc::Status(grpc::StatusCode::FAILED_PRECONDITION,
                        "Config not loaded");
  }

  for (const auto &path : request->paths()) {
    SignalId id = signal_ns_.resolve(path);
    if (id == INVALID_SIGNAL) {
      // Skip unknown signals (or could return error)
      continue;
    }

    auto signal = store_.read(id);
    auto *val = response->add_signals();
    val->set_path(path);
    val->set_value(signal.value);
    val->set_unit(signal.unit);
    val->set_physics_driven(store_.is_physics_driven(id));
  }

  return grpc::Status::OK;
}

// ============================================================================
// Reset RPC
// ============================================================================

grpc::Status
FluxGraphServiceImpl::Reset(grpc::ServerContext * /*context*/,
                            const fluxgraph::rpc::ResetRequest * /*request*/,
                            fluxgraph::rpc::ResetResponse *response) {

  std::lock_guard lock(state_mutex_);

  if (!loaded_) {
    response->set_success(false);
    response->set_error_message("Config not loaded");
    return grpc::Status(grpc::StatusCode::FAILED_PRECONDITION,
                        "Config not loaded");
  }

  try {
    // Reset engine state
    engine_.reset();
    store_.clear();
    for (SignalId id : physics_owned_signals_) {
      store_.mark_physics_driven(id, true);
    }
    sim_time_ = 0.0;

    // Reset tick/cached state
    tick_generation_ = 0;
    last_completed_generation_ = 0;
    last_completed_sim_time_ = 0.0;
    last_completed_commands_.clear();

    // Require all providers to resubmit generation 0 updates
    for (auto &[session_id, session] : sessions_) {
      (void)session_id;
      session.last_tick_generation = std::nullopt;
    }

    response->set_success(true);
    std::cout << "[FluxGraph] Reset complete\n";

    return grpc::Status::OK;

  } catch (const std::exception &e) {
    response->set_success(false);
    response->set_error_message(e.what());
    return grpc::Status(grpc::StatusCode::INTERNAL, e.what());
  }
}

// ============================================================================
// Check RPC (Health Check)
// ============================================================================

grpc::Status
FluxGraphServiceImpl::Check(grpc::ServerContext * /*context*/,
                            const fluxgraph::rpc::HealthCheckRequest *request,
                            fluxgraph::rpc::HealthCheckResponse *response) {

  if (request->service().empty() || request->service() == "fluxgraph") {
    response->set_status(fluxgraph::rpc::HealthCheckResponse::SERVING);
  } else {
    response->set_status(fluxgraph::rpc::HealthCheckResponse::SERVICE_UNKNOWN);
  }

  return grpc::Status::OK;
}

// ============================================================================
// Helper Methods
// ============================================================================

std::string
FluxGraphServiceImpl::generate_session_id(const std::string &provider_id) {
  auto now = std::chrono::system_clock::now();
  auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
                       now.time_since_epoch())
                       .count();

  std::random_device rd;
  std::mt19937 gen(rd());
  std::uniform_int_distribution<> dis(1000, 9999);

  std::ostringstream oss;
  oss << provider_id << "_" << timestamp << "_" << dis(gen);
  return oss.str();
}

void FluxGraphServiceImpl::convert_command(const fluxgraph::Command &cmd,
                                           fluxgraph::rpc::Command *pb_cmd) {

  pb_cmd->set_device(func_ns_.lookup_device(cmd.device));
  pb_cmd->set_function(func_ns_.lookup_function(cmd.function));

  for (const auto &[key, variant] : cmd.args) {
    auto &arg = (*pb_cmd->mutable_args())[key];

    if (std::holds_alternative<double>(variant)) {
      arg.set_double_val(std::get<double>(variant));
    } else if (std::holds_alternative<int64_t>(variant)) {
      arg.set_int_val(std::get<int64_t>(variant));
    } else if (std::holds_alternative<bool>(variant)) {
      arg.set_bool_val(std::get<bool>(variant));
    } else if (std::holds_alternative<std::string>(variant)) {
      arg.set_string_val(std::get<std::string>(variant));
    }
  }
}

void FluxGraphServiceImpl::prune_stale_sessions_locked(
    const std::string &active_session_id,
    std::chrono::steady_clock::time_point now) {
  for (auto it = sessions_.begin(); it != sessions_.end();) {
    if (it->first == active_session_id) {
      ++it;
      continue;
    }

    const auto age = std::chrono::duration_cast<std::chrono::milliseconds>(
        now - it->second.last_update);
    if (age > session_timeout_) {
      std::cerr << "[FluxGraph] Evicting stale provider session: provider_id="
                << it->second.provider_id << ", session_id=" << it->first
                << ", age_ms=" << age.count() << "\n";
      it = sessions_.erase(it);
    } else {
      ++it;
    }
  }
}

std::vector<fluxgraph::Command>
FluxGraphServiceImpl::filter_commands_for_session_locked(
    const std::string &session_id,
    const std::vector<fluxgraph::Command> &all_commands) {

  const auto session_it = sessions_.find(session_id);
  if (session_it == sessions_.end()) {
    return {};
  }

  const auto &device_ids = session_it->second.device_ids;
  if (device_ids.empty()) {
    return {};
  }

  std::vector<fluxgraph::Command> filtered;
  for (const auto &cmd : all_commands) {
    const std::string device_name = func_ns_.lookup_device(cmd.device);
    for (const auto &owned_device : device_ids) {
      if (device_name == owned_device) {
        filtered.push_back(cmd);
        break;
      }
    }
  }

  return filtered;
}

void FluxGraphServiceImpl::populate_tick_response_for_session_locked(
    const std::string &session_id, fluxgraph::rpc::TickResponse *response) {
  response->set_tick_occurred(true);
  response->set_sim_time_sec(last_completed_sim_time_);

  auto provider_commands =
      filter_commands_for_session_locked(session_id, last_completed_commands_);
  for (const auto &cmd : provider_commands) {
    auto *pb_cmd = response->add_commands();
    convert_command(cmd, pb_cmd);
  }
}

} // namespace fluxgraph::server

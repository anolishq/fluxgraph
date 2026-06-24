#pragma once

#include <grpcpp/grpcpp.h>

#include <chrono>
#include <condition_variable>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "fluxgraph.grpc.pb.h"
#include "fluxgraph/command.hpp"
#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/engine.hpp"
#include "fluxgraph/graph/compiler.hpp"

namespace fluxgraph::server {

/// Provider session information
struct ProviderSession {
    std::string provider_id;
    std::vector<std::string> device_ids;
    std::chrono::steady_clock::time_point last_update;
    std::optional<uint64_t> last_tick_generation;  // Last generation this provider
                                                   // submitted updates for
};

/// FluxGraph gRPC service implementation
///
/// Thread-safety: All RPC handlers are serialized with a single mutex.
/// Tick coordination: Server waits for all active providers to submit
/// UpdateSignals for the same generation before advancing one simulation tick.
class FluxGraphServiceImpl final : public fluxgraph::rpc::FluxGraph::Service {
public:
    explicit FluxGraphServiceImpl(double dt = 0.1);
    ~FluxGraphServiceImpl() override;

    // ========================================================================
    // RPC Handlers
    // ========================================================================

    grpc::Status LoadConfig(grpc::ServerContext *context, const fluxgraph::rpc::ConfigRequest *request,
                            fluxgraph::rpc::ConfigResponse *response) override;

    grpc::Status RegisterProvider(grpc::ServerContext *context, const fluxgraph::rpc::ProviderRegistration *request,
                                  fluxgraph::rpc::ProviderRegistrationResponse *response) override;

    grpc::Status UnregisterProvider(grpc::ServerContext *context, const fluxgraph::rpc::UnregisterRequest *request,
                                    fluxgraph::rpc::UnregisterResponse *response) override;

    grpc::Status UpdateSignals(grpc::ServerContext *context, const fluxgraph::rpc::SignalUpdates *request,
                               fluxgraph::rpc::TickResponse *response) override;

    grpc::Status ReadSignals(grpc::ServerContext *context, const fluxgraph::rpc::SignalRequest *request,
                             fluxgraph::rpc::SignalResponse *response) override;

    grpc::Status Reset(grpc::ServerContext *context, const fluxgraph::rpc::ResetRequest *request,
                       fluxgraph::rpc::ResetResponse *response) override;

    grpc::Status Check(grpc::ServerContext *context, const fluxgraph::rpc::HealthCheckRequest *request,
                       fluxgraph::rpc::HealthCheckResponse *response) override;

private:
    // ========================================================================
    // Core State
    // ========================================================================

    fluxgraph::Engine engine_;
    fluxgraph::SignalStore store_;
    fluxgraph::SignalNamespace signal_ns_;
    fluxgraph::FunctionNamespace func_ns_;

    // Thread safety
    std::mutex state_mutex_;
    std::condition_variable tick_cv_;  // Notified when tick completes
    uint64_t tick_generation_ = 0;     // Increments after each tick

    // Last completed tick snapshot (command queue is drained exactly once per
    // tick)
    uint64_t last_completed_generation_ = 0;
    double last_completed_sim_time_ = 0.0;
    std::vector<fluxgraph::Command> last_completed_commands_;

    // Configuration
    bool loaded_ = false;
    std::string current_config_hash_;
    double dt_;  // Runtime timestep in seconds
    double sim_time_ = 0.0;
    std::set<SignalId> protected_write_signals_;
    std::set<SignalId> physics_owned_signals_;

    // Provider tracking
    std::map<std::string, ProviderSession> sessions_;  // session_id -> session
    std::chrono::milliseconds session_timeout_{5000};

    // ========================================================================
    // Helper Methods (lock must already be held)
    // ========================================================================

    // Generate unique session ID for provider
    std::string generate_session_id(const std::string &provider_id);

    // Convert FluxGraph Command to protobuf Command
    void convert_command(const fluxgraph::Command &cmd, fluxgraph::rpc::Command *pb_cmd);

    // Remove stale sessions (except currently active session)
    void prune_stale_sessions_locked(const std::string &active_session_id, std::chrono::steady_clock::time_point now);

    // Filter commands for a specific provider session
    std::vector<fluxgraph::Command> filter_commands_for_session_locked(
        const std::string &session_id, const std::vector<fluxgraph::Command> &all_commands);

    // Populate TickResponse from last completed tick snapshot
    void populate_tick_response_for_session_locked(const std::string &session_id,
                                                   fluxgraph::rpc::TickResponse *response);
};

}  // namespace fluxgraph::server

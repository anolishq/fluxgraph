#include <atomic>
#include <chrono>
#include <csignal>
#include <fstream>
#include <thread>

#include "service.hpp"
#ifdef FLUXGRAPH_HAVE_GRPC_REFLECTION
#include <grpcpp/ext/proto_server_reflection_plugin.h>
#endif
#include <grpcpp/grpcpp.h>
#include <grpcpp/health_check_service_interface.h>

#include <iostream>
#include <memory>
#include <sstream>
#include <string>

// Global server instance for signal handler
std::unique_ptr<grpc::Server> g_server;

// Set by the signal handler; the shutdown watcher thread does the actual work.
std::atomic<bool> g_shutdown_requested{false};

// Signal handler for graceful shutdown. Must be async-signal-safe: only set a
// lock-free atomic flag here (no malloc/iostream/gRPC calls) — the watcher
// thread below performs the (signal-unsafe) Shutdown().
void signal_handler(int /*signal*/) { g_shutdown_requested.store(true); }

void print_usage(const char *prog_name) {
    std::cout << "FluxGraph gRPC Server\n\n";
    std::cout << "Usage: " << prog_name << " [OPTIONS]\n\n";
    std::cout << "Options:\n";
    std::cout << "  --port PORT        Server port (default: 50051)\n";
    std::cout << "  --config FILE      Preload config file (YAML or JSON)\n";
    std::cout << "  --dt SECONDS       Timestep in seconds (default: 0.1)\n";
    std::cout << "  --help             Show this help message\n";
}

std::string read_file(const std::string &path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        throw std::runtime_error("Failed to open file: " + path);
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

std::string get_format_from_path(const std::string &path) {
    size_t dot_pos = path.rfind('.');
    if (dot_pos == std::string::npos) {
        throw std::runtime_error("Cannot determine format from path: " + path);
    }
    std::string ext = path.substr(dot_pos + 1);
    if (ext == "yaml" || ext == "yml") {
        return "yaml";
    } else if (ext == "json") {
        return "json";
    } else {
        throw std::runtime_error("Unknown file extension: " + ext);
    }
}

int main(int argc, char *argv[]) {
    // CLI arguments
    int port = 50051;
    std::string config_path;
    double dt = 0.1;

    // Parse arguments
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--help") {
            print_usage(argv[0]);
            return 0;
        } else if (arg == "--port") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --port requires an argument\n";
                return 1;
            }
            port = std::stoi(argv[++i]);
        } else if (arg == "--config") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --config requires an argument\n";
                return 1;
            }
            config_path = argv[++i];
        } else if (arg == "--dt") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --dt requires an argument\n";
                return 1;
            }
            dt = std::stod(argv[++i]);
        } else {
            std::cerr << "Error: Unknown argument: " << arg << "\n";
            print_usage(argv[0]);
            return 1;
        }
    }

    // Validate arguments
    if (port < 1024 || port > 65535) {
        std::cerr << "Error: Port must be between 1024 and 65535\n";
        return 1;
    }
    if (dt <= 0.0) {
        std::cerr << "Error: Timestep must be positive\n";
        return 1;
    }

    std::cout << "=======================================================\n";
    std::cout << "FluxGraph gRPC Server\n";
    std::cout << "=======================================================\n";
    std::cout << "Port:      " << port << "\n";
    std::cout << "Timestep:  " << dt << " sec (" << (1.0 / dt) << " Hz)\n";
    if (!config_path.empty()) {
        std::cout << "Config:    " << config_path << "\n";
    }
    std::cout << "=======================================================\n\n";

    try {
        // Create service implementation
        auto service = std::make_unique<fluxgraph::server::FluxGraphServiceImpl>(dt);

        // Preload config if provided
        if (!config_path.empty()) {
            std::cout << "[FluxGraph] Preloading config from " << config_path << "...\n";

            std::string content = read_file(config_path);
            std::string format = get_format_from_path(config_path);

            fluxgraph::rpc::ConfigRequest request;
            request.set_config_content(content);
            request.set_format(format);

            fluxgraph::rpc::ConfigResponse response;
            grpc::ServerContext context;

            auto status = service->LoadConfig(&context, &request, &response);
            if (!status.ok()) {
                std::cerr << "[FluxGraph] Config load failed: " << status.error_message() << "\n";
                return 1;
            }

            std::cout << "[FluxGraph] Config loaded successfully\n\n";
        }

        // Enable health check service
        grpc::EnableDefaultHealthCheckService(true);

#ifdef FLUXGRAPH_HAVE_GRPC_REFLECTION
        // Enable server reflection (for grpcurl, etc.) when the grpc build provides
        // it (the x64-linux-tsan minimal grpc omits the reflection component).
        grpc::reflection::InitProtoReflectionServerBuilderPlugin();
#endif

        // Build server
        std::string server_address = "0.0.0.0:" + std::to_string(port);

        grpc::ServerBuilder builder;
        builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
        builder.RegisterService(service.get());

        g_server = builder.BuildAndStart();
        if (!g_server) {
            std::cerr << "[FluxGraph] Failed to start server\n";
            return 1;
        }

        std::cout << "[FluxGraph] Server listening on " << server_address << "\n";
        std::cout << "[FluxGraph] Press Ctrl+C to stop\n\n";

        // Register signal handlers
        std::signal(SIGINT, signal_handler);
        std::signal(SIGTERM, signal_handler);

        // Watcher thread turns the signal flag into a graceful Shutdown() off the
        // signal-handler context (Shutdown allocates and is not async-signal-safe).
        std::thread shutdown_watcher([] {
            while (!g_shutdown_requested.load()) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
            std::cout << "\n[FluxGraph] Shutdown signal received\n";
            if (g_server) {
                g_server->Shutdown();
            }
        });

        // Block until shutdown
        g_server->Wait();
        shutdown_watcher.join();

        std::cout << "[FluxGraph] Server stopped\n";
        return 0;

    } catch (const std::exception &e) {
        std::cerr << "[FluxGraph] Fatal error: " << e.what() << "\n";
        return 1;
    }
}

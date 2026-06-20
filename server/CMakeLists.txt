# FluxGraph gRPC Server
cmake_minimum_required(VERSION 3.20)

# Find required packages
find_package(Protobuf REQUIRED)
find_package(gRPC CONFIG REQUIRED)

# Protobuf files
set(PROTO_PATH "${CMAKE_SOURCE_DIR}/proto")
set(PROTO_FILE "${PROTO_PATH}/fluxgraph.proto")
set(GENERATED_PROTOBUF_PATH "${CMAKE_BINARY_DIR}/generated")

# Generate protobuf and gRPC code
file(MAKE_DIRECTORY ${GENERATED_PROTOBUF_PATH})

set(PROTO_SRCS "${GENERATED_PROTOBUF_PATH}/fluxgraph.pb.cc")
set(PROTO_HDRS "${GENERATED_PROTOBUF_PATH}/fluxgraph.pb.h")
set(GRPC_SRCS "${GENERATED_PROTOBUF_PATH}/fluxgraph.grpc.pb.cc")
set(GRPC_HDRS "${GENERATED_PROTOBUF_PATH}/fluxgraph.grpc.pb.h")

if(MSVC)
    # Suppress warnings from generated protobuf translation units only.
    set_source_files_properties(
        ${PROTO_SRCS} ${GRPC_SRCS}
        PROPERTIES COMPILE_OPTIONS "/wd4100;/wd4267"
    )
endif()

add_custom_command(
    OUTPUT ${PROTO_SRCS} ${PROTO_HDRS} ${GRPC_SRCS} ${GRPC_HDRS}
    COMMAND protobuf::protoc
    ARGS --grpc_out=${GENERATED_PROTOBUF_PATH}
         --cpp_out=${GENERATED_PROTOBUF_PATH}
         -I${PROTO_PATH}
         --plugin=protoc-gen-grpc=$<TARGET_FILE:gRPC::grpc_cpp_plugin>
         ${PROTO_FILE}
    DEPENDS ${PROTO_FILE}
    COMMENT "Generating protobuf and gRPC code"
)

# Server executable
add_executable(fluxgraph-server
    main.cpp
    service.cpp
    ${PROTO_SRCS}
    ${GRPC_SRCS}
)

# Include generated protobuf headers as SYSTEM so warnings in generated headers
# are not treated as project-source warnings.
target_include_directories(fluxgraph-server SYSTEM PRIVATE
    ${GENERATED_PROTOBUF_PATH}
)

# Link libraries
target_link_libraries(fluxgraph-server PRIVATE
    fluxgraph
    gRPC::grpc++
    protobuf::libprotobuf
)

# gRPC server reflection is an optional component (used for grpcurl/debugging,
# not by the RPC handlers or the integration tests). Some grpc builds — e.g. the
# minimal feature set vcpkg produces for the x64-linux-tsan triplet — omit it, so
# link it only when present rather than hard-requiring it.
if(TARGET gRPC::grpc++_reflection)
    target_link_libraries(fluxgraph-server PRIVATE gRPC::grpc++_reflection)
    target_compile_definitions(fluxgraph-server PRIVATE FLUXGRAPH_HAVE_GRPC_REFLECTION)
else()
    message(STATUS "gRPC::grpc++_reflection not available — building server without reflection")
endif()

# Compiler warnings
if(MSVC)
    target_compile_options(fluxgraph-server PRIVATE /W4)
else()
    target_compile_options(fluxgraph-server PRIVATE -Wall -Wextra -pedantic)
endif()

# Install server executable
install(TARGETS fluxgraph-server
    RUNTIME DESTINATION bin
)

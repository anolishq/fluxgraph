# The version 2 core (proposal: docs/semantics_spec_v2.md). Built only with FLUXGRAPH_BUILD_V2, beside the 1.x
# library and sharing nothing with it. Zero dependencies, as the 1.x core has.
add_library(fluxgraph_v2 STATIC
    block_delay.cpp
    block_formula.cpp
    block_hold.cpp
    block_integrate.cpp
    block_logic.cpp
    block_pid.cpp
    block_window.cpp
    blocks.cpp
    compiler.cpp
    engine.cpp
    exact.cpp
    formula.cpp
    setting.cpp
    state.cpp
)

target_include_directories(fluxgraph_v2 PUBLIC
    $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
)

target_compile_features(fluxgraph_v2 PUBLIC cxx_std_20)

# The warnings the 1.x target is built with.
if(MSVC)
    target_compile_options(fluxgraph_v2 PRIVATE /W4 /WX)
else()
    target_compile_options(fluxgraph_v2 PRIVATE -Wall -Wextra -Werror -pedantic)
endif()

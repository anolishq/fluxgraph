add_library(fluxgraph_viz_core STATIC
    viz_core/dot_emitter.cpp
)

target_include_directories(fluxgraph_viz_core PUBLIC
    $<BUILD_INTERFACE:${CMAKE_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

if(MSVC)
    target_compile_options(fluxgraph_viz_core PRIVATE /W4 /WX)
else()
    target_compile_options(fluxgraph_viz_core PRIVATE -Wall -Wextra -Werror -pedantic)
endif()

add_executable(fluxgraph_diagram
    fluxgraph_diagram/main.cpp
)

target_link_libraries(fluxgraph_diagram PRIVATE
    fluxgraph
    fluxgraph_viz_core
)

if(MSVC)
    target_compile_options(fluxgraph_diagram PRIVATE /W4 /WX)
else()
    target_compile_options(fluxgraph_diagram PRIVATE -Wall -Wextra -Werror -pedantic)
endif()

set_target_properties(fluxgraph_diagram PROPERTIES
    OUTPUT_NAME "fluxgraph-diagram"
)

install(TARGETS fluxgraph_viz_core
    EXPORT fluxgraphTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

install(TARGETS fluxgraph_diagram
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)


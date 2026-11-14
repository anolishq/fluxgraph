# Drives version 2 engines over stdin and stdout, for the conformance checks in conformance/cpp.
add_executable(fluxgraph_v2_driver
    main.cpp
)

target_link_libraries(fluxgraph_v2_driver PRIVATE fluxgraph_v2)

if(MSVC)
    target_compile_options(fluxgraph_v2_driver PRIVATE /W4 /WX)
else()
    target_compile_options(fluxgraph_v2_driver PRIVATE -Wall -Wextra -Werror -pedantic)
endif()

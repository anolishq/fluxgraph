# Checks of the version 2 core that have to be in C++: what a handle is good for, and what allocates.
add_executable(fluxgraph_v2_handles_and_memory
    handles_and_memory.cpp
)

target_link_libraries(fluxgraph_v2_handles_and_memory PRIVATE fluxgraph_v2)

if(MSVC)
    target_compile_options(fluxgraph_v2_handles_and_memory PRIVATE /W4 /WX)
else()
    target_compile_options(fluxgraph_v2_handles_and_memory PRIVATE -Wall -Wextra -Werror -pedantic)
endif()

if(FLUXGRAPH_JSON_ENABLED)
    add_executable(example_json_graph main.cpp)
    target_link_libraries(example_json_graph PRIVATE fluxgraph)
    
    # Copy bundled example graphs to build directory
    add_custom_command(TARGET example_json_graph POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_CURRENT_SOURCE_DIR}/graph.json
        $<TARGET_FILE_DIR:example_json_graph>/graph.json
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_CURRENT_SOURCE_DIR}/state_space_siso_discrete.json
        $<TARGET_FILE_DIR:example_json_graph>/state_space_siso_discrete.json
    )
endif()

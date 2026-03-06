# Usage Examples
#
# Example 1: Basic transform - Shows fundamental API (manual graph composition)
# Example 2: Thermal mass - Realistic physics simulation with models
# Example 3: JSON loader - Load graph from JSON file (requires -DFLUXGRAPH_JSON_ENABLED=ON)
# Example 4: YAML loader - Load graph from YAML file (requires -DFLUXGRAPH_YAML_ENABLED=ON)
# Example 5: Thermal RC2 - Coupled two-node thermal model
# Example 6: First-order process (dimensionless PT1)
# Example 7: Second-order process (dimensionless PT2)
# Example 8: Mass-spring-damper (translational mechanical model)
# Example 9: DC motor (electromechanical model)
# Example 10: State-space SISO discrete model (structured parameters)

add_subdirectory(01_basic_transform)
add_subdirectory(02_thermal_mass)
add_subdirectory(03_json_graph)
add_subdirectory(04_yaml_graph)
add_subdirectory(05_thermal_rc2)
add_subdirectory(06_first_order_process)
add_subdirectory(07_second_order_process)
add_subdirectory(08_mass_spring_damper)
add_subdirectory(09_dc_motor)
add_subdirectory(10_state_space_siso_discrete)

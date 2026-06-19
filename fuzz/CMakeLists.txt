# Fuzz targets (built only when ENABLE_FUZZING=ON; see cmake/AddFuzzTarget.cmake).
# Both loaders must be compiled into the fluxgraph library — the ci-fuzz preset
# sets FLUXGRAPH_JSON_ENABLED + FLUXGRAPH_YAML_ENABLED.

if(NOT FLUXGRAPH_JSON_ENABLED OR NOT FLUXGRAPH_YAML_ENABLED)
  message(FATAL_ERROR
    "ENABLE_FUZZING requires FLUXGRAPH_JSON_ENABLED and FLUXGRAPH_YAML_ENABLED "
    "(the fuzz targets exercise the JSON/YAML loaders).")
endif()

# JSON graph loader (fluxgraph::loaders::load_json_string).
anolis_add_fuzz_target(
  NAME fuzz_json_loader
  SOURCES fuzz_json_loader.cpp
  LINK fluxgraph
)

# YAML graph loader (fluxgraph::loaders::load_yaml_string).
anolis_add_fuzz_target(
  NAME fuzz_yaml_loader
  SOURCES fuzz_yaml_loader.cpp
  LINK fluxgraph
)

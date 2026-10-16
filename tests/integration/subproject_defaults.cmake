cmake_minimum_required(VERSION 3.20)

# Configures tests/integration/subproject, which embeds fluxgraph with
# add_subdirectory, in a fresh build tree. Passes when that configure
# succeeds with fluxgraph's tests and examples off by default.

foreach(var FLUXGRAPH_ROOT BINARY_DIR GENERATOR)
  if(NOT DEFINED ${var})
    message(FATAL_ERROR "${var} variable is required")
  endif()
endforeach()

file(REMOVE_RECURSE "${BINARY_DIR}")

set(ARGS
  -S "${FLUXGRAPH_ROOT}/tests/integration/subproject"
  -B "${BINARY_DIR}"
  -G "${GENERATOR}"
  "-DFLUXGRAPH_ROOT=${FLUXGRAPH_ROOT}"
)
if(PLATFORM)
  list(APPEND ARGS -A "${PLATFORM}")
endif()
if(TOOLSET)
  list(APPEND ARGS -T "${TOOLSET}")
endif()
if(MAKE_PROGRAM)
  list(APPEND ARGS "-DCMAKE_MAKE_PROGRAM=${MAKE_PROGRAM}")
endif()

execute_process(
  COMMAND "${CMAKE_COMMAND}" ${ARGS}
  RESULT_VARIABLE RESULT
  OUTPUT_VARIABLE STDOUT
  ERROR_VARIABLE STDERR
)
if(NOT RESULT EQUAL 0)
  message(FATAL_ERROR
    "Subproject configure failed (exit=${RESULT}).\nSTDOUT:\n${STDOUT}\nSTDERR:\n${STDERR}"
  )
endif()

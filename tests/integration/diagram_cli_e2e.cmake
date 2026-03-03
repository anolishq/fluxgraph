cmake_minimum_required(VERSION 3.20)

if(NOT DEFINED CLI)
  message(FATAL_ERROR "CLI variable is required")
endif()

if(NOT DEFINED INPUT)
  message(FATAL_ERROR "INPUT variable is required")
endif()

if(NOT DEFINED OUTPUT_DIR)
  message(FATAL_ERROR "OUTPUT_DIR variable is required")
endif()

file(MAKE_DIRECTORY "${OUTPUT_DIR}")

set(OUT_A "${OUTPUT_DIR}/diagram_a.dot")
set(OUT_B "${OUTPUT_DIR}/diagram_b.dot")

execute_process(
  COMMAND "${CLI}" --in "${INPUT}" --out "${OUT_A}" --format dot
  RESULT_VARIABLE RESULT_A
  OUTPUT_VARIABLE STDOUT_A
  ERROR_VARIABLE STDERR_A
)
if(NOT RESULT_A EQUAL 0)
  message(FATAL_ERROR
    "First diagram CLI run failed (exit=${RESULT_A}).\nSTDOUT:\n${STDOUT_A}\nSTDERR:\n${STDERR_A}"
  )
endif()

execute_process(
  COMMAND "${CLI}" --in "${INPUT}" --out "${OUT_B}" --format dot
  RESULT_VARIABLE RESULT_B
  OUTPUT_VARIABLE STDOUT_B
  ERROR_VARIABLE STDERR_B
)
if(NOT RESULT_B EQUAL 0)
  message(FATAL_ERROR
    "Second diagram CLI run failed (exit=${RESULT_B}).\nSTDOUT:\n${STDOUT_B}\nSTDERR:\n${STDERR_B}"
  )
endif()

if(NOT EXISTS "${OUT_A}" OR NOT EXISTS "${OUT_B}")
  message(FATAL_ERROR "Diagram CLI did not produce expected DOT outputs.")
endif()

file(READ "${OUT_A}" DOT_A)
file(READ "${OUT_B}" DOT_B)

if(NOT DOT_A STREQUAL DOT_B)
  message(FATAL_ERROR "Diagram CLI DOT outputs are not deterministic across runs.")
endif()

string(FIND "${DOT_A}" "digraph fluxgraph" DIGRAPH_POS)
if(DIGRAPH_POS EQUAL -1)
  message(FATAL_ERROR "DOT output does not contain expected graph header.")
endif()


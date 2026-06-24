// libFuzzer harness for the JSON graph loader
// (fluxgraph::loaders::load_json_string).
//
// load_json_string() takes the untrusted JSON text directly and throws
// std::runtime_error on malformed input, so we feed the fuzzer bytes straight
// in and swallow the expected parse exceptions; ASan watches the recursive
// parse + GraphSpec construction for memory errors.

#include <cstddef>
#include <cstdint>
#include <exception>
#include <string>

#include "fluxgraph/loaders/json_loader.hpp"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    std::string input(reinterpret_cast<const char *>(data), size);
    try {
        (void)fluxgraph::loaders::load_json_string(input);
    } catch (const std::exception &) {
        // Parse/validation errors are expected; only crashes/UB are bugs.
    }
    return 0;
}

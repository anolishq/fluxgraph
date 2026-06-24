// libFuzzer harness for the YAML graph loader
// (fluxgraph::loaders::load_yaml_string).
//
// load_yaml_string() takes the untrusted YAML text directly and throws
// std::runtime_error on malformed input (incl. the strict int/float scalar
// parsers), so we feed the fuzzer bytes straight in and swallow the expected
// parse exceptions; ASan watches for memory errors.

#include <cstddef>
#include <cstdint>
#include <exception>
#include <string>

#include "fluxgraph/loaders/yaml_loader.hpp"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    std::string input(reinterpret_cast<const char *>(data), size);
    try {
        (void)fluxgraph::loaders::load_yaml_string(input);
    } catch (const std::exception &) {
        // Parse/validation errors are expected; only crashes/UB are bugs.
    }
    return 0;
}

#include <bit>
#include <cstdint>

#include "fluxgraph/v2/block.hpp"

namespace fluxgraph::v2 {

void StateWriter::u64(std::uint64_t value) {
    for (int i = 0; i < 8; ++i) {
        bytes_.push_back(static_cast<std::uint8_t>((value >> (8 * i)) & 0xFFu));
    }
}

void StateWriter::f64(double value) { u64(std::bit_cast<std::uint64_t>(value)); }

void StateWriter::flag(bool value) { bytes_.push_back(value ? 1 : 0); }

void StateWriter::value(const Value &value) {
    bytes_.push_back(static_cast<std::uint8_t>(value.state));
    bytes_.push_back(static_cast<std::uint8_t>(value.type));
    flag(value.boolean);
    flag(value.timed);
    f64(value.number);
    u64(static_cast<std::uint64_t>(value.time));
}

bool StateReader::u64(std::uint64_t &value) {
    if (bytes_.size() < 8) {
        return false;
    }
    value = 0;
    for (int i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(bytes_[static_cast<std::size_t>(i)]) << (8 * i);
    }
    bytes_ = bytes_.subspan(8);
    return true;
}

bool StateReader::f64(double &value) {
    std::uint64_t bits = 0;
    if (!u64(bits)) {
        return false;
    }
    value = std::bit_cast<double>(bits);
    return true;
}

bool StateReader::flag(bool &value) {
    if (bytes_.empty() || bytes_[0] > 1) {
        return false;
    }
    value = bytes_[0] == 1;
    bytes_ = bytes_.subspan(1);
    return true;
}

bool StateReader::value(Value &value) {
    if (bytes_.size() < 2 || bytes_[0] > 3 || bytes_[1] > 1) {
        return false;
    }
    value.state = static_cast<State>(bytes_[0]);
    value.type = static_cast<Type>(bytes_[1]);
    bytes_ = bytes_.subspan(2);
    std::uint64_t time = 0;
    if (!flag(value.boolean) || !flag(value.timed) || !f64(value.number) || !u64(time)) {
        return false;
    }
    value.time = static_cast<Time>(time);
    return true;
}

}  // namespace fluxgraph::v2

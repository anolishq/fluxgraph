#include "fluxgraph/core/namespace.hpp"

#include <gtest/gtest.h>

using namespace fluxgraph;

class SignalNamespaceTest : public ::testing::Test {
protected:
    SignalNamespace ns;
};

TEST_F(SignalNamespaceTest, InternCreatesUniqueIds) {
    SignalId id1 = ns.intern("tempctl0/chamber/temperature");
    SignalId id2 = ns.intern("tempctl0/chamber/setpoint");

    EXPECT_NE(id1, id2);
    EXPECT_NE(id1, INVALID_SIGNAL);
    EXPECT_NE(id2, INVALID_SIGNAL);
}

TEST_F(SignalNamespaceTest, InternIsIdempotent) {
    SignalId id1 = ns.intern("tempctl0/chamber/temperature");
    SignalId id2 = ns.intern("tempctl0/chamber/temperature");

    EXPECT_EQ(id1, id2);
}

TEST_F(SignalNamespaceTest, ResolveReturnsExistingId) {
    std::string path = "tempctl0/chamber/temperature";
    SignalId id = ns.intern(path);

    EXPECT_EQ(ns.resolve(path), id);
}

TEST_F(SignalNamespaceTest, ResolveUnknownReturnsInvalid) { EXPECT_EQ(ns.resolve("unknown/path"), INVALID_SIGNAL); }

TEST_F(SignalNamespaceTest, LookupRoundTrip) {
    std::string path = "tempctl0/chamber/temperature";
    SignalId id = ns.intern(path);

    EXPECT_EQ(ns.lookup(id), path);
}

TEST_F(SignalNamespaceTest, LookupUnknownIdReturnsEmpty) { EXPECT_EQ(ns.lookup(999), ""); }

TEST_F(SignalNamespaceTest, Size) {
    EXPECT_EQ(ns.size(), 0);

    ns.intern("path1");
    EXPECT_EQ(ns.size(), 1);

    ns.intern("path2");
    EXPECT_EQ(ns.size(), 2);

    ns.intern("path1");  // Duplicate
    EXPECT_EQ(ns.size(), 2);
}

TEST_F(SignalNamespaceTest, AllPaths) {
    ns.intern("path1");
    ns.intern("path2");
    ns.intern("path3");

    auto paths = ns.all_paths();
    EXPECT_EQ(paths.size(), 3);

    // Verify all paths are present (order not guaranteed)
    EXPECT_NE(std::find(paths.begin(), paths.end(), "path1"), paths.end());
    EXPECT_NE(std::find(paths.begin(), paths.end(), "path2"), paths.end());
    EXPECT_NE(std::find(paths.begin(), paths.end(), "path3"), paths.end());
}

TEST_F(SignalNamespaceTest, Clear) {
    ns.intern("path1");
    ns.intern("path2");
    EXPECT_EQ(ns.size(), 2);

    ns.clear();
    EXPECT_EQ(ns.size(), 0);

    // After clear, resolve should return invalid
    EXPECT_EQ(ns.resolve("path1"), INVALID_SIGNAL);
}

class FunctionNamespaceTest : public ::testing::Test {
protected:
    FunctionNamespace fns;
};

TEST_F(FunctionNamespaceTest, InternDeviceCreatesUniqueIds) {
    DeviceId id1 = fns.intern_device("tempctl0");
    DeviceId id2 = fns.intern_device("motorctl0");

    EXPECT_NE(id1, id2);
    EXPECT_NE(id1, INVALID_DEVICE);
    EXPECT_NE(id2, INVALID_DEVICE);
}

TEST_F(FunctionNamespaceTest, InternDeviceIsIdempotent) {
    DeviceId id1 = fns.intern_device("tempctl0");
    DeviceId id2 = fns.intern_device("tempctl0");

    EXPECT_EQ(id1, id2);
}

TEST_F(FunctionNamespaceTest, InternFunctionCreatesUniqueIds) {
    FunctionId id1 = fns.intern_function("set_temperature");
    FunctionId id2 = fns.intern_function("set_power");

    EXPECT_NE(id1, id2);
    EXPECT_NE(id1, INVALID_FUNCTION);
    EXPECT_NE(id2, INVALID_FUNCTION);
}

TEST_F(FunctionNamespaceTest, InternFunctionIsIdempotent) {
    FunctionId id1 = fns.intern_function("set_temperature");
    FunctionId id2 = fns.intern_function("set_temperature");

    EXPECT_EQ(id1, id2);
}

TEST_F(FunctionNamespaceTest, LookupDeviceRoundTrip) {
    std::string name = "tempctl0";
    DeviceId id = fns.intern_device(name);

    EXPECT_EQ(fns.lookup_device(id), name);
}

TEST_F(FunctionNamespaceTest, LookupFunctionRoundTrip) {
    std::string name = "set_temperature";
    FunctionId id = fns.intern_function(name);

    EXPECT_EQ(fns.lookup_function(id), name);
}

TEST_F(FunctionNamespaceTest, ResolveDevice) {
    std::string name = "tempctl0";
    DeviceId id = fns.intern_device(name);

    EXPECT_EQ(fns.resolve_device(name), id);
    EXPECT_EQ(fns.resolve_device("unknown"), INVALID_DEVICE);
}

TEST_F(FunctionNamespaceTest, ResolveFunction) {
    std::string name = "set_temperature";
    FunctionId id = fns.intern_function(name);

    EXPECT_EQ(fns.resolve_function(name), id);
    EXPECT_EQ(fns.resolve_function("unknown"), INVALID_FUNCTION);
}

TEST_F(FunctionNamespaceTest, Clear) {
    fns.intern_device("dev1");
    fns.intern_function("func1");

    fns.clear();

    EXPECT_EQ(fns.resolve_device("dev1"), INVALID_DEVICE);
    EXPECT_EQ(fns.resolve_function("func1"), INVALID_FUNCTION);
}

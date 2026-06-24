#include "fluxgraph/command.hpp"

#include <gtest/gtest.h>

using namespace fluxgraph;

TEST(CommandTest, DefaultConstruction) {
    Command cmd;
    EXPECT_EQ(cmd.device, INVALID_DEVICE);
    EXPECT_EQ(cmd.function, INVALID_FUNCTION);
    EXPECT_TRUE(cmd.args.empty());
}

TEST(CommandTest, ConstructionWithIds) {
    Command cmd(10, 20);
    EXPECT_EQ(cmd.device, 10);
    EXPECT_EQ(cmd.function, 20);
    EXPECT_TRUE(cmd.args.empty());
}

TEST(CommandTest, StoreDoubleArg) {
    Command cmd(1, 2);
    cmd.args["temperature"] = 25.0;

    EXPECT_TRUE(std::holds_alternative<double>(cmd.args["temperature"]));
    EXPECT_EQ(std::get<double>(cmd.args["temperature"]), 25.0);
}

TEST(CommandTest, StoreInt64Arg) {
    Command cmd(1, 2);
    cmd.args["count"] = int64_t(100);

    EXPECT_TRUE(std::holds_alternative<int64_t>(cmd.args["count"]));
    EXPECT_EQ(std::get<int64_t>(cmd.args["count"]), 100);
}

TEST(CommandTest, StoreBoolArg) {
    Command cmd(1, 2);
    cmd.args["enable"] = true;

    EXPECT_TRUE(std::holds_alternative<bool>(cmd.args["enable"]));
    EXPECT_TRUE(std::get<bool>(cmd.args["enable"]));
}

TEST(CommandTest, StoreStringArg) {
    Command cmd(1, 2);
    cmd.args["mode"] = std::string("auto");

    EXPECT_TRUE(std::holds_alternative<std::string>(cmd.args["mode"]));
    EXPECT_EQ(std::get<std::string>(cmd.args["mode"]), "auto");
}

TEST(CommandTest, MultipleArgs) {
    Command cmd(5, 10);
    cmd.args["temperature"] = 100.0;
    cmd.args["ramp_rate"] = 2.5;
    cmd.args["enable"] = true;
    cmd.args["mode"] = std::string("manual");

    EXPECT_EQ(cmd.args.size(), 4);
    EXPECT_EQ(std::get<double>(cmd.args["temperature"]), 100.0);
    EXPECT_EQ(std::get<double>(cmd.args["ramp_rate"]), 2.5);
    EXPECT_TRUE(std::get<bool>(cmd.args["enable"]));
    EXPECT_EQ(std::get<std::string>(cmd.args["mode"]), "manual");
}

TEST(CommandTest, VariantCopyable) {
    Variant v1 = 42.0;
    Variant v2 = v1;

    EXPECT_TRUE(std::holds_alternative<double>(v2));
    EXPECT_EQ(std::get<double>(v2), 42.0);
}

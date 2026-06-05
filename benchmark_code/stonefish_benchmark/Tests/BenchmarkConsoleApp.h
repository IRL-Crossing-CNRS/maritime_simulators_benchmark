/*
    Stonefish Benchmark
    BenchmarkConsoleApp.h
*/
#pragma once
#include <core/ConsoleSimulationApp.h>
#include "BenchmarkManager.h"

class BenchmarkConsoleApp : public sf::ConsoleSimulationApp
{
public:
    BenchmarkConsoleApp(std::string dataDirPath, BenchmarkManager* sim);

protected:
    void LoopInternal() override;
};

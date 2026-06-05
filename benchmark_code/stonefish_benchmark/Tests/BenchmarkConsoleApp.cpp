/*
    Stonefish Benchmark
    BenchmarkConsoleApp.cpp
*/
#include "BenchmarkConsoleApp.h"

#include <chrono>
#include <thread>

BenchmarkConsoleApp::BenchmarkConsoleApp(std::string dataDirPath, BenchmarkManager* sim)
    : ConsoleSimulationApp("Benchmark", dataDirPath, sim)
{
}

void BenchmarkConsoleApp::LoopInternal()
{
    BenchmarkManager* mgr = static_cast<BenchmarkManager*>(getSimulationManager());

    if (mgr->isMeasurementDone())
    {
        if (getState() == sf::SimulationState::RUNNING)
            StopSimulation();
        Quit();
        return;
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(100));
}

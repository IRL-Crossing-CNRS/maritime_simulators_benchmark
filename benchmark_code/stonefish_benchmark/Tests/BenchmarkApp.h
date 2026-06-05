/*
    Stonefish Benchmark
    BenchmarkApp.h
*/
#pragma once
#include <core/GraphicalSimulationApp.h>
#include "BenchmarkManager.h"

class BenchmarkApp : public sf::GraphicalSimulationApp
{
public:
    BenchmarkApp(std::string dataDirPath,
                 sf::RenderSettings renderSettings,
                 sf::HelperSettings helperSettings,
                 BenchmarkManager* sim);

    double getDisplayFPS();

protected:
    // Called every frame — we use it to stop the app once measurement is done
    void DoHUD() override;
};

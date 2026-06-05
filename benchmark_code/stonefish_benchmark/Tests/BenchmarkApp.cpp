/*
    Stonefish Benchmark
    BenchmarkApp.cpp
*/
#include "BenchmarkApp.h"
#include <graphics/IMGUI.h>

BenchmarkApp::BenchmarkApp(std::string dataDirPath,
                           sf::RenderSettings renderSettings,
                           sf::HelperSettings helperSettings,
                           BenchmarkManager* sim)
    : GraphicalSimulationApp("Benchmark", dataDirPath, renderSettings, helperSettings, sim)
{
}

double BenchmarkApp::getDisplayFPS()
{
    const double drawingTimeMs = getDrawingTime();
    return drawingTimeMs > 1e-9 ? 1000.0 / drawingTimeMs : 0.0;
}

void BenchmarkApp::DoHUD()
{
    GraphicalSimulationApp::DoHUD();

    BenchmarkManager* mgr = static_cast<BenchmarkManager*>(getSimulationManager());

    // Quit the application once the manager signals measurement is complete
    if (mgr->isMeasurementDone())
        Quit();
}

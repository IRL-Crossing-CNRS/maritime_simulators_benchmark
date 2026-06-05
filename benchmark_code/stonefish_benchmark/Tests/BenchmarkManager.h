/*
    Stonefish Benchmark
    BenchmarkManager.h
*/
#pragma once
#include <core/SimulationManager.h>
#include <core/FeatherstoneRobot.h>
#include <string>
#include <vector>
#include <chrono>
#include <fstream>
#include <functional>

// Protocol definitions
// A: user perception limit  stepsPerSecond=5   (200ms step) RTF=1 rendering
// B: physics limit          stepsPerSecond=33  (30ms step)  RTF=1 rendering
// C: AI training            stepsPerSecond=33  (30ms step)  RTF target rendering
// D: AI training headless   stepsPerSecond=33  (30ms step)  RTF target no rendering

struct StepMetrics
{
    double wall_time_s;   // wall clock time of this sample (s since epoch)
    double sim_time_s;    // simulation time (s)
    double rtf;           // sim_dt / wall_dt
    double step_time_ms;  // wall time of the physics step (ms)
    int    agent_count;
    double fps;           // rendering FPS at this step (0.0 when headless)
};

// Drives a timed Stonefish benchmark: warm-up N steps, then measure M steps,
// collecting per-step RTF, wall time, and FPS. Spawns numAgents BlueROV2 vehicles.
// Call setFpsGetter() before the simulation loop to enable FPS logging (rendering runs).
// Leave it unset for headless runs — fps field stays 0.0 in all collected metrics.
class BenchmarkManager : public sf::SimulationManager
{
public:
    // stepsPerSecond: passed directly to SimulationManager
    //   Protocol A: 5.0   (1/0.200)
    //   Protocol B,C,D: 33.0  (1/0.030)
    BenchmarkManager(sf::Scalar stepsPerSecond, int numAgents);

    void BuildScenario() override;
    void SimulationStepCompleted(sf::Scalar timeStep) override;

    // Called by App/main to retrieve collected metrics
    const std::vector<StepMetrics>& getMetrics() const { return metrics_; }
    int getAgentCount() const { return numAgents_; }

    // Warmup / measure control
    void setWarmupSteps(int n)  { warmupSteps_ = n; }
    void setMeasureSteps(int n) { measureSteps_ = n; }
    bool isMeasurementDone() const { return measureDone_; }

    // Set a callable that returns the current rendering FPS.
    // Called every physics step during measurement.
    // Leave unset (or nullptr) for headless runs — fps stays 0.0.
    void setFpsGetter(std::function<double()> getter) { fpsGetter_ = std::move(getter); }

private:
    // Spawns one GIRONA500-class robot (vehicle + thrusters, no sensors)
    void spawnRobot(const std::string& name, const sf::Transform& pose);

    // Spawns one BlueROV2-class robot (vehicle + thrusters, no sensors)
    void spawnBlueROV2(const std::string& name, const sf::Transform& pose);

    int numAgents_;

    // Timing state
    using Clock = std::chrono::steady_clock;
    Clock::time_point lastWallTime_;
    double            lastSimTime_{0.0};
    bool              timingInit_{false};

    // Step counting
    int  stepCount_{0};
    int  warmupSteps_{50};    // default: discard first 50 steps
    int  measureSteps_{300};  // default: measure 300 steps then stop
    bool measureDone_{false};

    // Camera tracking
    glm::vec3 currentCameraCenter_{0.0f, 0.0f, -1.0f};

    std::vector<StepMetrics>  metrics_;
    std::function<double()>   fpsGetter_;  // null → headless, fps stays 0.0
};
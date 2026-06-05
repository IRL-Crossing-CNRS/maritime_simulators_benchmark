/*
    Stonefish Benchmark
    BenchmarkManager.cpp
*/
#include "BenchmarkManager.h"

#include <core/FeatherstoneRobot.h>
#include <entities/solids/Box.h>
#include <entities/solids/Cylinder.h>
#include <entities/solids/Sphere.h>
#include <entities/solids/Polyhedron.h>
#include <entities/solids/Compound.h>
#include <entities/statics/Plane.h>
#include <entities/forcefields/Uniform.h>
#include <entities/MovingEntity.h>
#include <actuators/Thruster.h>
#include <graphics/OpenGLTrackball.h>
#include <utils/SystemUtil.hpp>
#include <utils/UnitSystem.h>

#include <iostream>
#include <iomanip>
#include <sstream>
#include <cmath>
#include <csignal>
#include <atomic>

// Global flag for Ctrl+C handling
static std::atomic<bool> g_shouldStop(false);

static void signalHandler(int sig)
{
    if (sig == SIGINT) {
        std::cout << "\n[Benchmark] Ctrl+C received. Requesting clean shutdown...\n";
        g_shouldStop = true;
    }
}

// ─── Constructor ─────────────────────────────────────────────────────────────

BenchmarkManager::BenchmarkManager(sf::Scalar stepsPerSecond, int numAgents)
    : SimulationManager(stepsPerSecond, sf::Solver::SI, sf::CollisionFilter::EXCLUSIVE)
    , numAgents_(numAgents)
{
    std::signal(SIGINT, signalHandler);
}

// ─── BuildScenario ───────────────────────────────────────────────────────────

void BenchmarkManager::BuildScenario()
{
    // ── Materials ────────────────────────────────────────────────────────────
    CreateMaterial("Dummy",      sf::UnitSystem::Density(sf::CGS, sf::MKS, 0.9), 0.3);
    CreateMaterial("Fiberglass", sf::UnitSystem::Density(sf::CGS, sf::MKS, 1.5), 0.9);
    CreateMaterial("Rock",       sf::UnitSystem::Density(sf::CGS, sf::MKS, 3.0), 0.6);
    SetMaterialsInteraction("Dummy",      "Dummy",      0.5, 0.2);
    SetMaterialsInteraction("Fiberglass", "Fiberglass", 0.5, 0.2);
    SetMaterialsInteraction("Rock",       "Rock",       0.9, 0.7);
    SetMaterialsInteraction("Fiberglass", "Dummy",      0.5, 0.2);
    SetMaterialsInteraction("Rock",       "Dummy",      0.6, 0.4);
    SetMaterialsInteraction("Rock",       "Fiberglass", 0.6, 0.4);

    // ── Looks ────────────────────────────────────────────────────────────────
    CreateLook("yellow",     sf::Color::RGB(1.f, 0.9f, 0.f),  0.3f, 0.f);
    CreateLook("grey",       sf::Color::RGB(0.3f, 0.3f, 0.3f),0.4f, 0.5f);
    CreateLook("black",      sf::Color::RGB(0.1f, 0.1f, 0.1f),0.4f, 0.5f);
    CreateLook("br2",        sf::Color::RGB(0.5f, 0.5f, 0.5f),0.4f, 0.5f, 0.f, sf::GetDataPath() + "bluerov2/br2.png");
    CreateLook("manipulator",sf::Color::RGB(0.2f, 0.15f, 0.1f),0.6f,0.8f);
    CreateLook("propeller",  sf::Color::RGB(1.f, 1.f, 1.f),   0.3f, 0.f);
    CreateLook("seabed",     sf::Color::RGB(0.7f, 0.7f, 0.5f),0.9f, 0.f, 0.f, "",
               sf::GetDataPath() + "sand_normal.png");

    // ── Ocean + uniform current ───────────────────────────────────────────────
    EnableOcean(0.0);
    getOcean()->setWaterType(0.2);
    getOcean()->AddVelocityField(new sf::Uniform(sf::Vector3(1.0, 0.0, 0.0)));
    getOcean()->EnableCurrents();
    getAtmosphere()->SetSunPosition(0.0, 60.0);

    // ── Sea floor ────────────────────────────────────────────────────────────
    sf::Plane* seabed = new sf::Plane("Seabed", sf::Scalar(1000), "Rock", "seabed");
    AddStaticEntity(seabed, sf::Transform(sf::IQ(), sf::Vector3(0, 0, 15.0)));

    // ── Spawn N robots in a grid ─────────────────────────────────────────────
    const double spacing = 6.0; // metres between robots
    const int    cols    = (int)std::ceil(std::sqrt((double)numAgents_));

    for (int i = 0; i < numAgents_; ++i)
    {
        double x = (i % cols) * spacing;
        double y = (i / cols) * spacing;
        double z = 0.0; // Spawn at water surface level

        std::ostringstream name;
        name << "BlueROV2" << std::setw(4) << std::setfill('0') << i;

        sf::Transform pose(sf::IQ(), sf::Vector3(x, y, z));
        spawnBlueROV2(name.str(), pose);
    }

    // ── Center camera on robot grid ───────────────────────────────────────────
    if (getTrackball() != nullptr)
    {
        glm::vec3 desiredCenter(0.0f, 0.0f, 0.0f);
        glm::vec3 initialCenter(0.0f, 0.0f, -1.0f);
        getTrackball()->MoveCenter(desiredCenter - initialCenter);
        currentCameraCenter_ = desiredCenter;
        getTrackball()->Rotate(glm::angleAxis(-glm::radians(30.0f), glm::vec3(1.0f, 0.0f, 0.0f)));
    }
}

// ─── spawnRobot ──────────────────────────────────────────────────────────────
// Spawns a GIRONA500-class robot: three-hull frame + 5 thrusters (sway, 2×surge, 2×heave).
// No sensors are added — benchmark measures physics overhead only.
// Mass values (ScalePhysicalPropertiesToArbitraryMass) are tuned to match the
// GIRONA500 neutral-buoyancy configuration: battery 70 kg, side cylinders 20 kg each.

void BenchmarkManager::spawnRobot(const std::string& name, const sf::Transform& pose)
{
    sf::PhysicsSettings phy;
    phy.mode       = sf::PhysicsMode::SUBMERGED;
    phy.collisions = true;

    phy.buoyancy = false;
    sf::Box* hullB = new sf::Box(
        name + "/HullBottom", phy, sf::Vector3(1.10, 0.34, 0.18), sf::I4(),
        "Fiberglass", "yellow", sf::Scalar(0.01));

    sf::Box* hullP = new sf::Box(
        name + "/HullPort", phy, sf::Vector3(1.10, 0.16, 0.18), sf::I4(),
        "Fiberglass", "yellow", sf::Scalar(0.01));

    sf::Box* hullS = new sf::Box(
        name + "/HullStarboard", phy, sf::Vector3(1.10, 0.16, 0.18), sf::I4(),
        "Fiberglass", "yellow", sf::Scalar(0.01));

    sf::Box* vBarStern = new sf::Box(
        name + "/VBarStern", phy, sf::Vector3(0.18, 0.08, 0.08), sf::I4(),
        "Dummy", "grey", sf::Scalar(0.01));

    sf::Box* vBarBow = new sf::Box(
        name + "/VBarBow", phy, sf::Vector3(0.18, 0.08, 0.08), sf::I4(),
        "Dummy", "grey", sf::Scalar(0.01));

    phy.buoyancy = true;
    sf::Cylinder* ductSway = new sf::Cylinder(
        name + "/DuctSway", phy, 0.12, 0.08, sf::I4(), "Dummy", "black", sf::Scalar(0.01));

    sf::Cylinder* ductSurgeP = new sf::Cylinder(
        name + "/DuctSurgePort", phy, 0.12, 0.08, sf::I4(), "Dummy", "black", sf::Scalar(0.01));

    sf::Cylinder* ductSurgeS = new sf::Cylinder(
        name + "/DuctSurgeStarboard", phy, 0.12, 0.08, sf::I4(), "Dummy", "black", sf::Scalar(0.01));

    sf::Cylinder* ductHeaveS = new sf::Cylinder(
        name + "/DuctHeaveStern", phy, 0.12, 0.08, sf::I4(), "Dummy", "black", sf::Scalar(0.01));

    sf::Cylinder* ductHeaveB = new sf::Cylinder(
        name + "/DuctHeaveBow", phy, 0.12, 0.08, sf::I4(), "Dummy", "black", sf::Scalar(0.01));

    sf::Cylinder* batteryCyl = new sf::Cylinder(
        name + "/BatteryCylinder", phy, 0.13, 0.6, sf::I4(), "Dummy", "manipulator");
    batteryCyl->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(70));

    sf::Cylinder* portCyl = new sf::Cylinder(
        name + "/PortCylinder", phy, 0.13, 1.0, sf::I4(), "Dummy", "manipulator");
    portCyl->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(20));

    sf::Cylinder* starboardCyl = new sf::Cylinder(
        name + "/StarboardCylinder", phy, 0.13, 1.0, sf::I4(), "Dummy", "manipulator");
    starboardCyl->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(20));

    sf::Compound* vehicle = new sf::Compound(name + "/Vehicle", phy, hullB, sf::I4());
    vehicle->AddExternalPart(hullP,     sf::Transform(sf::IQ(), sf::Vector3(0, -0.35, -0.7)));
    vehicle->AddExternalPart(hullS,     sf::Transform(sf::IQ(), sf::Vector3(0,  0.35, -0.7)));
    vehicle->AddExternalPart(vBarStern, sf::Transform(sf::IQ(), sf::Vector3(-0.25, 0.0, -0.15)));
    vehicle->AddExternalPart(vBarBow,   sf::Transform(sf::IQ(), sf::Vector3( 0.30, 0.0, -0.15)));
    vehicle->AddExternalPart(ductSway,  sf::Transform(sf::Quaternion(M_PI_2, M_PI, 0),
                                            sf::Vector3(-0.0137, 0.0307, -0.38)));
    vehicle->AddExternalPart(ductSurgeP,sf::Transform(sf::Quaternion(0, 0, M_PI),
                                            sf::Vector3(-0.2807, -0.2587, -0.38)));
    vehicle->AddExternalPart(ductSurgeS,sf::Transform(sf::Quaternion(0, 0, 0),
                                            sf::Vector3(-0.2807,  0.2587, -0.38)));
    vehicle->AddExternalPart(ductHeaveS,sf::Transform(sf::Quaternion( M_PI_2, -M_PI_2, 0),
                                            sf::Vector3(-0.5337, 0.0, -0.6747)));
    vehicle->AddExternalPart(ductHeaveB,sf::Transform(sf::Quaternion(-M_PI_2, -M_PI_2, 0),
                                            sf::Vector3( 0.5837, 0.0, -0.6747)));
    vehicle->AddInternalPart(batteryCyl,  sf::Transform(sf::Quaternion(0, M_PI_2, 0),
                                            sf::Vector3(-0.1, 0, 0)));
    vehicle->AddInternalPart(portCyl,     sf::Transform(sf::Quaternion(0, M_PI_2, 0),
                                            sf::Vector3(0.0, -0.35, -0.7)));
    vehicle->AddInternalPart(starboardCyl,sf::Transform(sf::Quaternion(0, M_PI_2, 0),
                                            sf::Vector3(0.0,  0.35, -0.7)));
    vehicle->setDisplayInternalParts(false);

    std::shared_ptr<sf::Cylinder> propeller = std::make_shared<sf::Cylinder>(
        name + "/Propeller", phy, 0.09, 0.02, sf::I4(), "Dummy", "propeller");

    std::array<std::string, 5> thrNames = {
        "ThrusterSway", "ThrusterSurgePort", "ThrusterSurgeStarboard",
        "ThrusterHeaveStern", "ThrusterHeaveBow"
    };
    std::array<sf::Thruster*, 5> thrusters;
    for (size_t i = 0; i < thrNames.size(); ++i)
    {
        auto rotorDyn   = std::make_shared<sf::MechanicalPI>(1.0, 10.0, 5.0, 5.0);
        auto thrustModel= std::make_shared<sf::FDThrust>(
            0.18, 0.48, 0.48, 0.05, true, getOcean()->getLiquid().density);
        thrusters[i] = new sf::Thruster(
            thrNames[i], propeller, rotorDyn, thrustModel,
            0.18, true, 105.0, true, true);
    }

    sf::Robot* robot = new sf::FeatherstoneRobot(name, false);
    robot->DefineLinks(vehicle, {});
    robot->BuildKinematicStructure();

    robot->AddLinkActuator(thrusters[0], name + "/Vehicle",
        sf::Transform(sf::Quaternion(M_PI_2, M_PI, 0),
                      sf::Vector3(-0.0137, 0.0307, -0.38)));
    robot->AddLinkActuator(thrusters[1], name + "/Vehicle",
        sf::Transform(sf::IQ(), sf::Vector3(-0.2807, -0.2587, -0.38)));
    robot->AddLinkActuator(thrusters[2], name + "/Vehicle",
        sf::Transform(sf::IQ(), sf::Vector3(-0.2807,  0.2587, -0.38)));
    robot->AddLinkActuator(thrusters[3], name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, -M_PI_2, 0),
                      sf::Vector3(-0.5337, 0.0, -0.6747)));
    robot->AddLinkActuator(thrusters[4], name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, -M_PI_2, 0),
                      sf::Vector3( 0.5837, 0.0, -0.6747)));

    AddRobot(robot, pose);
}

// ─── spawnBlueROV2 ───────────────────────────────────────────────────────────
// Spawns a BlueROV2 Heavy Configuration: polyhedron hull + ring + 4 corner buoyancy
// boxes + 3 ballast spheres + 8 thrusters (4 horizontal at ±45°, 4 vertical).
// Geometry and thruster positions are taken from the BlueROV2 Heavy datasheet.
// Assets (bluerov2_phy.obj, bluerov2_ring.obj) come from:
//   https://github.com/bvibhav/stonefish_bluerov2

void BenchmarkManager::spawnBlueROV2(const std::string& name, const sf::Transform& pose)
{
    sf::PhysicsSettings phy;
    phy.mode       = sf::PhysicsMode::SUBMERGED;
    phy.collisions = true;

    phy.buoyancy = true;
    sf::Polyhedron* hull = new sf::Polyhedron(
        name + "/HullBottom", phy,
        sf::GetDataPath() + "bluerov2/bluerov2_phy.obj",
        sf::Scalar(1.0),
        sf::I4(), "Fiberglass", "br2");

    sf::Polyhedron* heavyFit = new sf::Polyhedron(
        name + "/HeavyFit", phy,
        sf::GetDataPath() + "bluerov2/bluerov2_ring.obj",
        sf::Scalar(1.0),
        sf::I4(), "Fiberglass", "black");

    phy.buoyancy = true;
    sf::Box* backLeft = new sf::Box(
        name + "/BackLeft",  phy, sf::Vector3(0.2, 0.15, 0.091),
        sf::I4(), "Neutral", "grey", sf::Scalar(0.001));
    backLeft->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(0.025));

    sf::Box* backRight = new sf::Box(
        name + "/BackRight", phy, sf::Vector3(0.2, 0.15, 0.091),
        sf::I4(), "Neutral", "grey", sf::Scalar(0.001));
    backRight->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(0.025));

    sf::Box* frontLeft = new sf::Box(
        name + "/FrontLeft", phy, sf::Vector3(0.2, 0.15, 0.091),
        sf::I4(), "Neutral", "grey", sf::Scalar(0.001));
    frontLeft->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(0.025));

    sf::Box* frontRight = new sf::Box(
        name + "/FrontRight", phy, sf::Vector3(0.2, 0.15, 0.091),
        sf::I4(), "Neutral", "grey", sf::Scalar(0.001));
    frontRight->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(0.025));

    phy.buoyancy = false;
    sf::Sphere* weightCenter = new sf::Sphere(
        name + "/WeightCenter", phy, 0.01, sf::I4(), "Steel", "black");
    weightCenter->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(2.0));

    sf::Sphere* weightLeft = new sf::Sphere(
        name + "/WeightLeft",  phy, 0.01, sf::I4(), "Steel", "black");
    weightLeft->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(1.0));

    sf::Sphere* weightRight = new sf::Sphere(
        name + "/WeightRight", phy, 0.01, sf::I4(), "Steel", "black");
    weightRight->ScalePhysicalPropertiesToArbitraryMass(sf::Scalar(1.0));

    sf::Compound* vehicle = new sf::Compound(name + "/Vehicle", phy, hull, sf::I4());
    vehicle->AddExternalPart(heavyFit,
        sf::Transform(sf::IQ(), sf::Vector3(0.0, 0.0, 0.03)));
    vehicle->AddInternalPart(backLeft,
        sf::Transform(sf::IQ(), sf::Vector3(-0.1, -0.1,  0.0)));
    vehicle->AddInternalPart(backRight,
        sf::Transform(sf::IQ(), sf::Vector3(-0.1,  0.1,  0.0)));
    vehicle->AddInternalPart(frontLeft,
        sf::Transform(sf::IQ(), sf::Vector3( 0.09,-0.1,  0.0)));
    vehicle->AddInternalPart(frontRight,
        sf::Transform(sf::IQ(), sf::Vector3( 0.09, 0.1,  0.0)));
    vehicle->AddInternalPart(weightCenter,
        sf::Transform(sf::IQ(), sf::Vector3( 0.0,    0.0,   0.1)));
    vehicle->AddInternalPart(weightLeft,
        sf::Transform(sf::IQ(), sf::Vector3( 0.0,   -0.075, 0.1)));
    vehicle->AddInternalPart(weightRight,
        sf::Transform(sf::IQ(), sf::Vector3( 0.0,    0.075, 0.1)));
    vehicle->setDisplayInternalParts(false);

    phy.buoyancy = false;
    std::shared_ptr<sf::Cylinder> propeller = std::make_shared<sf::Cylinder>(
        name + "/Propeller", phy, 0.038, 0.02, sf::I4(), "Neutral", "blue");

    auto makeThruster = [&](const std::string& thrName, bool rightProp) -> sf::Thruster*
    {
        auto rotorDyn    = std::make_shared<sf::MechanicalPI>(1.0, 10.0, 5.0, 5.0);
        auto thrustModel = std::make_shared<sf::FDThrust>(
            0.076, 0.167, 0.167, 0.016, rightProp,
            getOcean()->getLiquid().density);
        return new sf::Thruster(
            thrName, propeller, rotorDyn, thrustModel,
            0.076, rightProp, 3600.0, true, true);
    };

    sf::Thruster* tFrontRight     = makeThruster(name + "/ThrFrontRight",     true);
    sf::Thruster* tFrontLeft      = makeThruster(name + "/ThrFrontLeft",      true);
    sf::Thruster* tBackRight      = makeThruster(name + "/ThrBackRight",      false);
    sf::Thruster* tBackLeft       = makeThruster(name + "/ThrBackLeft",       false);
    sf::Thruster* tDiveFrontRight = makeThruster(name + "/ThrDiveFrontRight", true);
    sf::Thruster* tDiveFrontLeft  = makeThruster(name + "/ThrDiveFrontLeft",  false);
    sf::Thruster* tDiveBackRight  = makeThruster(name + "/ThrDiveBackRight",  false);
    sf::Thruster* tDiveBackLeft   = makeThruster(name + "/ThrDiveBackLeft",   true);

    sf::Robot* robot = new sf::FeatherstoneRobot(name, false);
    robot->DefineLinks(vehicle, {});
    robot->BuildKinematicStructure();

    robot->AddLinkActuator(tFrontRight, name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, 0, -M_PI/4),
                      sf::Vector3( 0.1355,  0.1,   0.0725)));
    robot->AddLinkActuator(tFrontLeft, name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, 0,  M_PI/4),
                      sf::Vector3( 0.1355, -0.1,   0.0725)));
    robot->AddLinkActuator(tBackRight, name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, 0, -3*M_PI/4),
                      sf::Vector3(-0.1475,  0.1,   0.0725)));
    robot->AddLinkActuator(tBackLeft, name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, 0,  3*M_PI/4),
                      sf::Vector3(-0.1475, -0.1,   0.0725)));
    robot->AddLinkActuator(tDiveFrontRight, name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, -M_PI_2, 0),
                      sf::Vector3( 0.12,  0.218, 0.0)));
    robot->AddLinkActuator(tDiveFrontLeft, name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, -M_PI_2, 0),
                      sf::Vector3( 0.12, -0.218, 0.0)));
    robot->AddLinkActuator(tDiveBackRight, name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, -M_PI_2, 0),
                      sf::Vector3(-0.12,  0.218, 0.0)));
    robot->AddLinkActuator(tDiveBackLeft, name + "/Vehicle",
        sf::Transform(sf::Quaternion(0, -M_PI_2, 0),
                      sf::Vector3(-0.12, -0.218, 0.0)));

    AddRobot(robot, pose);
}


// ─── SimulationStepCompleted ─────────────────────────────────────────────────

void BenchmarkManager::SimulationStepCompleted(sf::Scalar timeStep)
{
    if (g_shouldStop)
    {
        std::cout << "\n[Benchmark] Ctrl+C received. Stopping simulation...\n";
        measureDone_ = true;
        return;
    }

    if (measureDone_) return;

    ++stepCount_;

    // ── Warm-up phase ─────────────────────────────────────────────────────────
    if (stepCount_ <= warmupSteps_)
    {
        if (stepCount_ == warmupSteps_)
        {
            lastWallTime_ = Clock::now();
            lastSimTime_  = getSimulationTime();
            timingInit_   = true;
            std::cout << "[Benchmark] Warmup done. Starting measurement.\n";
        }
        return;
    }

    if (!timingInit_) return;

    // ── Measure phase ─────────────────────────────────────────────────────────
    Clock::time_point nowWall = Clock::now();
    double nowSim = getSimulationTime();

    double wallDt     = std::chrono::duration<double>(nowWall - lastWallTime_).count();
    double simDt      = nowSim - lastSimTime_;
    double rtf        = (wallDt > 1e-9) ? simDt / wallDt : 0.0;
    double stepTimeMs = wallDt * 1000.0;

    // Query FPS from the rendering app (0.0 when headless or not yet set)
    double fps = fpsGetter_ ? fpsGetter_() : 0.0;

    StepMetrics m;
    m.wall_time_s  = std::chrono::duration<double>(nowWall.time_since_epoch()).count();
    m.sim_time_s   = nowSim;
    m.rtf          = rtf;
    m.step_time_ms = stepTimeMs;
    m.agent_count  = numAgents_;
    m.fps          = fps;
    metrics_.push_back(m);

    lastWallTime_ = nowWall;
    lastSimTime_  = nowSim;

    // ── Stop after measureSteps_ ──────────────────────────────────────────────
    if ((stepCount_ - warmupSteps_) >= measureSteps_)
    {
        measureDone_ = true;
        std::cout << "[Benchmark] Measurement complete ("
                  << measureSteps_ << " steps, "
                  << numAgents_ << " agents).\n";
        StopSimulation();
    }
}
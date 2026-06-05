/*
    Stonefish Benchmark — main.cpp

    Usage:
      ./Benchmark --protocol A [--agents 8] [--warmup 50] [--steps 300]
      ./Benchmark --protocol B --agents 4
      ./Benchmark --protocol C --agents 16
      ./Benchmark --protocol D --agents 32   (headless, no window)
      ./Benchmark --protocol A --search      (binary search for max RTF-OK agents)
      ./Benchmark --config benchmark_config.json

    Protocols:
      A  step=200ms  RTF=1  rendering   (human-in-the-loop)
      B  step=30ms   RTF=1  rendering   (control loop)
      C  step=30ms   target rendering (AI training)
      D  step=30ms   target headless  (AI training, fastest)
*/

#include "BenchmarkManager.h"
#include "BenchmarkApp.h"
#include "BenchmarkConsoleApp.h"

#include <core/ConsoleSimulationApp.h>
#include <nlohmann/json.hpp>

#include <iostream>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>
#include <numeric>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <memory>
#include <filesystem>
#include <cctype>
#include <optional>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <csignal>
#include <sys/wait.h>
#include <thread>
#include <chrono>
#include <unistd.h>

// ─── Protocol config ──────────────────────────────────────────────────────────

struct ProtocolConfig
{
    char        id;
    std::string name;
    sf::Scalar  stepsPerSecond;
    double      targetRTF;
    bool        rendering;
    double      rtfThreshold;
};

static ProtocolConfig makeProtocol(char id)
{
    switch (id)
    {
    case 'A': return {'A', "A-human-loop",  sf::Scalar(5.0),  1.0,    true,  0.98};
    case 'B': return {'B', "B-control",     sf::Scalar(33.0), 1.0,    true,  0.98};
    case 'C': return {'C', "C-ai-render",   sf::Scalar(33.0),  26.0, true,  0.0};
    case 'D': return {'D', "D-ai-headless", sf::Scalar(33.0), 20.0, false, 0.0};
    default:  throw std::runtime_error(std::string("Unknown protocol: ") + id);
    }
}

static std::vector<ProtocolConfig> makeAllProtocols()
{
    return { makeProtocol('A'), makeProtocol('B'), makeProtocol('C'), makeProtocol('D') };
}

static bool isValidProtocolId(char id)
{
    char upper = std::toupper(static_cast<unsigned char>(id));
    return upper == 'A' || upper == 'B' || upper == 'C' || upper == 'D';
}

// ─── Metrics aggregation ──────────────────────────────────────────────────────

struct RunResult
{
    char        protocolId  = 'A';
    double      stepSizeMs  = 0.0;
    double      targetRTF   = 0.0;
    bool        rendering   = false;
    std::string status      = "ok";
    int         agents      = 0;
    double      meanRTF     = 0.0;
    double      minRTF      = 0.0;
    double      p95RTF      = 0.0;
    double      meanStepMs  = 0.0;
    double      p95StepMs   = 0.0;
    bool        rtfOk       = false;
    double      meanFPS     = 0.0;
    double      maxFPS      = 0.0;
    double      p95FPS      = 0.0;
};

static std::string formatTargetRTFValue(double targetRTF);

static double percentile(std::vector<double> v, double p)
{
    if (v.empty()) return 0.0;
    std::sort(v.begin(), v.end());
    size_t idx = static_cast<size_t>(std::ceil(p * v.size()));
    if (idx > 0) --idx;
    return v[std::min(idx, v.size() - 1)];
}

static RunResult aggregate(const ProtocolConfig& proto,
                           const std::vector<StepMetrics>& m,
                           int agents)
{
    RunResult r{};
    r.protocolId = proto.id;
    r.stepSizeMs = 1000.0 / proto.stepsPerSecond;
    r.targetRTF  = proto.targetRTF;
    r.rendering  = proto.rendering;
    r.agents     = agents;
    if (m.empty()) return r;

    std::vector<double> rtfs, steps, fpss;
    for (auto& s : m)
    {
        rtfs.push_back(s.rtf);
        steps.push_back(s.step_time_ms);
        fpss.push_back(s.fps);
    }

    r.meanRTF    = std::accumulate(rtfs.begin(),  rtfs.end(),  0.0) / rtfs.size();
    r.meanStepMs = std::accumulate(steps.begin(), steps.end(), 0.0) / steps.size();
    r.minRTF     = *std::min_element(rtfs.begin(), rtfs.end());
    r.p95RTF     = percentile(rtfs,  0.95);
    r.p95StepMs  = percentile(steps, 0.95);

    if (proto.rendering)
    {
        r.meanFPS = std::accumulate(fpss.begin(), fpss.end(), 0.0) / fpss.size();
        r.maxFPS  = *std::max_element(fpss.begin(), fpss.end());
        r.p95FPS  = percentile(fpss, 0.95);
    }

    // rtfOk: uncapped protocols (rtfThreshold==0) are always ok
    const double threshold = (proto.rtfThreshold <= 0.0) ? -1.0 : proto.rtfThreshold;
    r.rtfOk = (threshold <= 0.0) || (r.meanRTF >= threshold);
    return r;
}

// ─── CSV logger (child-side temp file only) ───────────────────────────────────

class CSVLogger
{
public:
    CSVLogger(const std::string& path, bool append = false)
        : ofs_(path, std::ios::out | (append ? std::ios::app : std::ios::trunc))
    {
        if (!append)
            ofs_ << "protocol,agents,wall_time_s,sim_time_s,rtf,step_time_ms,fps\n";
    }

    void write(const std::string& proto, const StepMetrics& m)
    {
        ofs_ << proto         << ','
             << m.agent_count << ','
             << std::fixed << std::setprecision(6)
             << m.wall_time_s  << ','
             << m.sim_time_s   << ','
             << m.rtf          << ','
             << m.step_time_ms << ','
             << m.fps          << '\n';
    }

private:
    std::ofstream ofs_;
};

// ─── Summary CSV: upsert-aware, write-through ────────────────────────────────
//
// Key design: flush() is called after EVERY write(), not just in the
// destructor. This means the file is always up-to-date on disk. A Ctrl+C
// between two runs therefore loses nothing — the signal handler just needs
// to exit cleanly without corrupting the file.

class SummaryCSVLogger
{
public:
    static constexpr const char* HEADER =
        "protocol,agents,step_size_ms,target_rtf,rendering,"
        "mean_rtf,min_rtf,p95_rtf,mean_step_ms,p95_step_ms,"
        "mean_fps,max_fps,p95_fps,"
        "rtf_ok,status";

    explicit SummaryCSVLogger(const std::string& path)
        : path_(path)
    {
        loadExisting();
    }

    ~SummaryCSVLogger() { flush(); }

    void write(const std::string& proto, const RunResult& r)
    {
        Key k{proto, r.agents, formatTargetRTFValue(r.targetRTF)};
        rows_[k] = formatRow(proto, r);
        flush();   // write-through: persist immediately after every completed run
    }

    void flush()
    {
        std::ofstream ofs(path_, std::ios::out | std::ios::trunc);
        if (!ofs) return;
        ofs << HEADER << '\n';
        for (auto& [key, line] : rows_)
            ofs << line << '\n';
    }

private:
    struct Key
    {
        std::string proto;
        int         agents;
        std::string targetRTF;

        bool operator<(const Key& other) const
        {
            if (proto != other.proto) return proto < other.proto;
            if (agents != other.agents) return agents < other.agents;
            return targetRTF < other.targetRTF;
        }
    };

    std::string                path_;
    std::map<Key, std::string> rows_;

    void loadExisting()
    {
        std::ifstream ifs(path_);
        if (!ifs) return;

        std::string line;
        std::getline(ifs, line); // skip header

        while (std::getline(ifs, line))
        {
            if (line.empty()) continue;
            std::istringstream ss(line);
            std::string proto, agentsTok, stepSizeTok, targetRTFTok;
            std::getline(ss, proto,     ',');
            std::getline(ss, agentsTok, ',');
            std::getline(ss, stepSizeTok, ',');
            std::getline(ss, targetRTFTok, ',');
            if (proto.empty() || agentsTok.empty() || targetRTFTok.empty()) continue;

            try
            {
                int agents = std::stoi(agentsTok);
                Key k{proto, agents, targetRTFTok};
                rows_.emplace(k, line);
            }
            catch (...) {}
        }
    }

    static std::string formatRow(const std::string& proto, const RunResult& r)
    {
        std::ostringstream os;
        os << proto         << ','
           << r.agents      << ','
           << std::fixed << std::setprecision(6)
           << r.stepSizeMs  << ','
           << r.targetRTF   << ','
           << (r.rendering ? "true" : "false") << ','
           << r.meanRTF     << ','
           << r.minRTF      << ','
           << r.p95RTF      << ','
           << r.meanStepMs  << ','
           << r.p95StepMs   << ','
           << r.meanFPS     << ','
           << r.maxFPS      << ','
           << r.p95FPS      << ','
           << (r.rtfOk ? "true" : "false") << ','
           << r.status;
        return os.str();
    }
};

// ─── Global pointer for signal handler (parent process only) ─────────────────
//
// Because write-through already keeps the file current, the signal handler
// only needs to prevent a double-flush from the destructor and exit cleanly.
// It must NOT call flush() itself — signal handlers must only use async-
// signal-safe functions, and file I/O is not async-signal-safe.

static SummaryCSVLogger* g_summaryLogger = nullptr;

static void parentSigHandler(int sig)
{
    // Announce on stderr using only the async-signal-safe write() syscall.
    const char* msg =
        "\n[Benchmark] Interrupted — completed runs already saved to summary.\n";
    (void)::write(STDERR_FILENO, msg, strlen(msg));

    // Prevent the destructor from doing a redundant (and potentially racy) flush.
    // The file is already up-to-date thanks to write-through.
    g_summaryLogger = nullptr;

    // Re-raise so the shell sees the correct exit status (e.g. 130 for SIGINT).
    std::signal(sig, SIG_DFL);
    raise(sig);
}

// ─── Utilities ────────────────────────────────────────────────────────────────

static std::string sanitizeName(const std::string& value)
{
    std::string out = value;
    for (char& c : out)
        if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '-' || c == '_'))
            c = '_';
    return out;
}

static bool parseBoolToken(const std::string& token)
{
    return token == "true" || token == "1" || token == "yes";
}

static std::string formatTargetRTFToken(double targetRTF)
{
    std::ostringstream os;
    os << std::fixed << std::setprecision(6) << targetRTF;
    std::string token = os.str();
    std::replace(token.begin(), token.end(), '.', 'p');
    return token;
}

static std::string formatTargetRTFValue(double targetRTF)
{
    std::ostringstream os;
    os << std::fixed << std::setprecision(6) << targetRTF;
    return os.str();
}

static ProtocolConfig withTargetRTF(ProtocolConfig proto,
                                    const std::optional<double>& targetRTFOverride)
{
    if (targetRTFOverride.has_value())
        proto.targetRTF = *targetRTFOverride;
    return proto;
}

static RunResult makeFailureResult(const ProtocolConfig& proto, int agents,
                                   const std::string& status)
{
    RunResult r{};
    r.protocolId = proto.id;
    r.stepSizeMs = 1000.0 / proto.stepsPerSecond;
    r.targetRTF  = proto.targetRTF;
    r.rendering  = proto.rendering;
    r.status     = status;
    r.agents     = agents;
    r.rtfOk      = false;
    return r;
}

static std::string decodeChildStatus(int rc)
{
    if (rc == -1) return "launch_error";
    if (WIFSIGNALED(rc)) return "signal_" + std::to_string(WTERMSIG(rc));
    if (WIFEXITED(rc))   return "exit_"   + std::to_string(WEXITSTATUS(rc));
    return "failed";
}

// ─── Resolve step count from seconds or explicit steps ───────────────────────

static int resolveSteps(const ProtocolConfig& proto,
                        double measureSeconds,
                        int    measureSteps)
{
    if (measureSeconds > 0.0)
        return static_cast<int>(std::round(measureSeconds * proto.stepsPerSecond));
    return measureSteps;
}

// ─── Args ────────────────────────────────────────────────────────────────────

struct ConfigRun
{
    char             protocol;
    std::vector<int> agents;
    std::optional<double> targetRTF;
};

struct Args
{
    char        protocol       = 'A';
    int         agents         = 1;
    int         warmup         = 50;
    int         steps          = 300;
    double      measureSeconds = -1.0;
    std::string summary_csv    = "results/benchmark_summary.csv";
    std::string output_dir     = "results";
    std::string config_path    = "";
    bool        search         = false;
    bool        autoSweep      = false;
    bool        allProtocols   = false;
    bool        appendOutput   = true;
    int         minAgents      = 1;
    int         maxAgents      = 32;
    int         agentStep      = 1;
    bool        childRun       = false;
    std::string childCsv       = "";
    std::optional<double> targetRTFOverride;
    std::vector<ConfigRun> configRuns;
};

static void resolveDefaultOutputPaths(Args& args)
{
    const std::filesystem::path d(args.output_dir);
    args.summary_csv = (d / "benchmark_summary.csv").string();
}

// ─── Argument parsing ─────────────────────────────────────────────────────────

static void printUsage(const char* exe)
{
    std::cout <<
        "Usage: " << exe << " [options]\n\n"
        "  --protocol A|B|C|D      Benchmark protocol (default: A)\n"
        "  --config PATH           JSON config file\n"
        "  --agents N              Number of agents (default: 1)\n"
        "  --warmup N              Warmup steps (default: 50)\n"
        "  --steps N               Measure steps (default: 300)\n"
        "  --measure-seconds N     Measure duration in seconds (overrides --steps;\n"
        "                          step count is derived per-protocol from steps/sec)\n"
        "  --target-rtf N          Override the protocol target RTF for this run\n"
        "  --output-dir PATH       Folder for CSV outputs (default: results)\n"
        "  --search                Binary-search for max RTF-OK agent count\n"
        "  --auto-sweep            Linear sweep, stop when real-time fails\n"
        "  --all-protocols         Run A, B, C, D\n"
        "  --min-agents N          Search lower bound (default: 1)\n"
        "  --max-agents N          Search upper bound (default: 32)\n"
        "  --agent-step N          Sweep increment (default: 1)\n"
        "  --help                  Show this message\n\n";
}

static std::vector<int> parseAgentList(const nlohmann::json& arrayValue)
{
    if (!arrayValue.is_array())
        throw std::runtime_error("JSON field 'agents' must be an array");
    std::vector<int> agents;
    for (const auto& item : arrayValue)
    {
        if (!item.is_number_integer())
            throw std::runtime_error("JSON field 'agents' must contain integers");
        int v = item.get<int>();
        if (v <= 0) throw std::runtime_error("JSON agent counts must be > 0");
        agents.push_back(v);
    }
    if (agents.empty()) throw std::runtime_error("JSON field 'agents' must not be empty");
    return agents;
}

static void loadConfigFile(const std::string& path, Args& args)
{
    std::ifstream ifs(path);
    if (!ifs) throw std::runtime_error("Cannot open config file: " + path);

    nlohmann::json root;
    try { ifs >> root; }
    catch (const nlohmann::json::parse_error& e)
    { throw std::runtime_error(std::string("JSON parse error: ") + e.what()); }

    if (!root.is_object())
        throw std::runtime_error("Benchmark config root must be a JSON object");

    if (root.contains("output_dir"))    args.output_dir = root.at("output_dir").get<std::string>();
    if (root.contains("warmup_steps"))  args.warmup     = root.at("warmup_steps").get<int>();
    if (root.contains("agent_step"))    args.agentStep  = root.at("agent_step").get<int>();
    if (root.contains("min_agents"))    args.minAgents  = root.at("min_agents").get<int>();
    if (root.contains("max_agents"))    args.maxAgents  = root.at("max_agents").get<int>();
    if (root.contains("auto_sweep"))    args.autoSweep  = root.at("auto_sweep").get<bool>();

    if (root.contains("measure_seconds"))
    {
        args.measureSeconds = root.at("measure_seconds").get<double>();
        if (args.measureSeconds <= 0.0)
            throw std::runtime_error("JSON field 'measure_seconds' must be > 0");
        args.steps = -1;
    }
    else if (root.contains("measure_steps"))
    {
        args.steps          = root.at("measure_steps").get<int>();
        args.measureSeconds = -1.0;
    }

    resolveDefaultOutputPaths(args);

    if (root.contains("runs"))
    {
        const auto& runs = root.at("runs");
        if (!runs.is_array())
            throw std::runtime_error("JSON field 'runs' must be an array");

        args.configRuns.clear();
        for (const auto& rv : runs)
        {
            if (!rv.is_object())
                throw std::runtime_error("Each run in 'runs' must be an object");
            if (!rv.contains("protocol"))
                throw std::runtime_error("Each run must contain 'protocol'");

            std::string ps = rv.at("protocol").get<std::string>();
            if (ps.size() != 1 || !isValidProtocolId(ps[0]))
                throw std::runtime_error("Run protocol must be one of A, B, C, D (case-insensitive)");

            ConfigRun run{};
            run.protocol = std::toupper(static_cast<unsigned char>(ps[0]));

            if (rv.contains("agents"))
                run.agents = parseAgentList(rv.at("agents"));
            else if (rv.contains("agent"))
            {
                int v = rv.at("agent").get<int>();
                if (v <= 0) throw std::runtime_error("JSON field 'agent' must be > 0");
                run.agents = {v};
            }
            else
                throw std::runtime_error("Each run must contain 'agents' or 'agent'");

            if (rv.contains("target_rtf"))
            {
                run.targetRTF = rv.at("target_rtf").get<double>();
                if (*run.targetRTF < 0.0)
                    throw std::runtime_error("JSON field 'target_rtf' must be >= 0");
            }

            args.configRuns.push_back(run);
        }
    }
}

static Args parseArgs(int argc, const char* argv[])
{
    Args a;
    for (int i = 1; i < argc; ++i)
    {
        std::string arg = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) throw std::runtime_error("Expected value after " + arg);
            return argv[++i];
        };
        auto nextInt    = [&]() { return std::stoi(next()); };
        auto nextDouble = [&]() { return std::stod(next()); };

        if      (arg == "--help" || arg == "-h") { printUsage(argv[0]); std::exit(0); }
        else if (arg == "--config")          { a.config_path    = next(); }
        else if (arg == "--protocol")        { a.protocol       = std::toupper(
                                                  static_cast<unsigned char>(next()[0])); }
        else if (arg == "--agents")          { a.agents         = nextInt(); }
        else if (arg == "--warmup")          { a.warmup         = nextInt(); }
        else if (arg == "--steps")           { a.steps          = nextInt(); }
        else if (arg == "--measure-seconds") { a.measureSeconds = nextDouble(); }
        else if (arg == "--summary-csv")     { a.summary_csv    = next(); }
        else if (arg == "--output-dir")      { a.output_dir     = next(); }
        else if (arg == "--search")          { a.search         = true; }
        else if (arg == "--auto-sweep")      { a.autoSweep      = true; }
        else if (arg == "--all-protocols")   { a.allProtocols   = true; }
        else if (arg == "--append-output")   { a.appendOutput   = parseBoolToken(next()); }
        else if (arg == "--min-agents")      { a.minAgents      = nextInt(); }
        else if (arg == "--max-agents")      { a.maxAgents      = nextInt(); }
        else if (arg == "--agent-step")      { a.agentStep      = nextInt(); }
        else if (arg == "--child-run")       { a.childRun       = true; }
        else if (arg == "--child-csv")       { a.childCsv       = next(); }
        else if (arg == "--target-rtf")
        {
            a.targetRTFOverride = nextDouble();
            if (*a.targetRTFOverride < 0.0)
                throw std::runtime_error("--target-rtf must be >= 0");
        }
        else throw std::runtime_error("Unknown argument: " + arg);
    }
    resolveDefaultOutputPaths(a);
    return a;
}

// ─── Single simulation run (child process only) ───────────────────────────────

static std::vector<StepMetrics> runOnce(
    const ProtocolConfig& proto,
    int agents,
    const std::string& dataDirPath,
    int warmupSteps,
    int measureSteps,
    CSVLogger& logger)
{
    BenchmarkManager mgr(proto.stepsPerSecond, agents);
    mgr.setRealtimeFactor(proto.targetRTF);
    mgr.setWarmupSteps(warmupSteps);
    mgr.setMeasureSteps(measureSteps);

    if (proto.rendering)
    {
        sf::RenderSettings s;
        s.windowW      = 960;
        s.windowH      = 540;
        s.aa           = sf::RenderQuality::LOW;
        s.shadows      = sf::RenderQuality::DISABLED;
        s.ao           = sf::RenderQuality::DISABLED;
        s.atmosphere   = sf::RenderQuality::LOW;
        s.ocean        = sf::RenderQuality::LOW;
        s.ssr          = sf::RenderQuality::DISABLED;
        s.verticalSync = false;

        sf::HelperSettings h;
        h.showFluidDynamics   = false;
        h.showCoordSys        = false;
        h.showBulletDebugInfo = false;
        h.showSensors         = false;
        h.showActuators       = false;
        h.showForces          = false;

        BenchmarkApp app(dataDirPath, s, h, &mgr);

        mgr.setFpsGetter([&app]() -> double {
            return static_cast<double>(app.getDisplayFPS());
        });

        app.Run();
    }
    else
    {
        BenchmarkConsoleApp app(dataDirPath, &mgr);
        app.Run();
    }

    for (auto& m : mgr.getMetrics())
        logger.write(proto.name, m);

    return mgr.getMetrics();
}

// ─── Subprocess runner (parent side) ─────────────────────────────────────────

static RunResult runInSubprocess(
    const ProtocolConfig& proto,
    int agents,
    const std::string& dataDirPath,
    int warmupSteps,
    int measureSteps,
    const std::string& outDir,
    SummaryCSVLogger& summaryLogger,
    const std::string& selfExePath)
{
    const std::string baseName =
        "protocol_" + std::string(1, proto.id) +
        "_agents_" + std::to_string(agents) +
        "_rtf_" + formatTargetRTFToken(proto.targetRTF);
    const std::filesystem::path runCsvPath =
        std::filesystem::path(outDir) / (sanitizeName(baseName) + "_steps.csv");

    std::vector<std::string> argVec = {
        selfExePath,
        "--child-run",
        "--protocol",   std::string(1, proto.id),
        "--agents",     std::to_string(agents),
        "--warmup",     std::to_string(warmupSteps),
        "--steps",      std::to_string(measureSteps),
        "--target-rtf", formatTargetRTFValue(proto.targetRTF),
        "--output-dir", outDir,
        "--child-csv",  runCsvPath.string(),
    };
    std::vector<const char*> argv;
    for (auto& a : argVec) argv.push_back(a.c_str());
    argv.push_back(nullptr);

    std::cout << "[Benchmark] Launching child: protocol=" << proto.id
              << " agents=" << agents
              << " target_rtf=" << proto.targetRTF
              << " measure_steps=" << measureSteps << "\n";

    pid_t pid = fork();
    if (pid < 0)
    {
        std::cerr << "[ERROR] fork() failed: " << strerror(errno) << "\n";
        RunResult r = makeFailureResult(proto, agents, "fork_error");
        summaryLogger.write(proto.name, r);
        return r;
    }

    if (pid == 0)
    {
        // Child: restore default signal handlers before exec so the child
        // process is not affected by the parent's Ctrl+C handler.
        std::signal(SIGINT,  SIG_DFL);
        std::signal(SIGTERM, SIG_DFL);
        execv(selfExePath.c_str(), const_cast<char* const*>(argv.data()));
        std::cerr << "[ERROR] execv failed: " << strerror(errno) << "\n";
        _exit(1);
    }

    // Parent: wait for child to finish
    int status = 0;
    waitpid(pid, &status, 0);

    std::this_thread::sleep_for(std::chrono::milliseconds(2000));

    if (WIFSIGNALED(status) || (WIFEXITED(status) && WEXITSTATUS(status) != 0))
    {
        std::string reason = decodeChildStatus(status);
        std::cerr << "[Benchmark] Child exited abnormally: " << reason << "\n";
        RunResult r = makeFailureResult(proto, agents, reason);
        summaryLogger.write(proto.name, r);   // write-through: persisted immediately
        return r;
    }

    // ── Parse temp CSV written by the child ───────────────────────────────────
    std::vector<StepMetrics> metrics;
    {
        std::ifstream ifs(runCsvPath);
        if (!ifs)
        {
            std::cerr << "[Benchmark] Child CSV not found: " << runCsvPath << "\n";
            RunResult r = makeFailureResult(proto, agents, "no_csv");
            summaryLogger.write(proto.name, r);
            return r;
        }

        std::string line;
        std::getline(ifs, line); // skip header
        while (std::getline(ifs, line))
        {
            if (line.empty()) continue;
            std::istringstream ss(line);
            std::string tok;
            StepMetrics m;
            // columns: protocol, agents, wall_time_s, sim_time_s, rtf, step_time_ms, fps
            std::getline(ss, tok, ',');
            std::getline(ss, tok, ','); m.agent_count  = std::stoi(tok);
            std::getline(ss, tok, ','); m.wall_time_s  = std::stod(tok);
            std::getline(ss, tok, ','); m.sim_time_s   = std::stod(tok);
            std::getline(ss, tok, ','); m.rtf          = std::stod(tok);
            std::getline(ss, tok, ','); m.step_time_ms = std::stod(tok);
            std::getline(ss, tok, ','); m.fps          = std::stod(tok);
            metrics.push_back(m);
        }
    }

    // Aggregate and write-through to summary
    RunResult r = aggregate(proto, metrics, agents);
    summaryLogger.write(proto.name, r);   // persisted immediately
    return r;
}

// ─── Print helpers ────────────────────────────────────────────────────────────

static void printResult(const RunResult& r, const ProtocolConfig& proto)
{
    std::cout << "  agents=" << std::setw(4) << r.agents
              << "  RTF mean=" << std::fixed << std::setprecision(3) << r.meanRTF
              << "  min="      << r.minRTF
              << "  p95="      << r.p95RTF
              << "  step_p95=" << std::setprecision(2) << r.p95StepMs << "ms";
    if (proto.rendering)
        std::cout << "  FPS mean=" << std::setprecision(1) << r.meanFPS
                  << "  max=" << r.maxFPS
                  << "  p95=" << r.p95FPS;
    std::cout << (r.rtfOk ? "  ✓" : "  ✗")
              << (r.status == "ok" ? "" : "  [" + r.status + "]")
              << "\n";
}

static void printSummary(const std::vector<RunResult>& history,
                         const ProtocolConfig& proto)
{
    const bool showFps = proto.rendering;

    std::cout << "\n══════════════════════════════════════════════════════════════════\n";
    std::cout << "  SUMMARY  –  Protocol " << proto.name << "\n";
    std::cout << "══════════════════════════════════════════════════════════════════\n";
    std::cout << std::setw(8)  << "agents"
              << std::setw(11) << "mean_RTF"
              << std::setw(10) << "min_RTF"
              << std::setw(10) << "p95_RTF"
              << std::setw(13) << "step_p95_ms";
    if (showFps)
        std::cout << std::setw(11) << "mean_FPS"
                  << std::setw(10) << "max_FPS"
                  << std::setw(10) << "p95_FPS";
    std::cout << std::setw(7) << "ok?\n";
    std::cout << std::string(showFps ? 89 : 59, '-') << "\n";

    for (auto& r : history)
    {
        std::cout << std::setw(8) << r.agents
                  << std::fixed << std::setprecision(3)
                  << std::setw(11) << r.meanRTF
                  << std::setw(10) << r.minRTF
                  << std::setw(10) << r.p95RTF
                  << std::setprecision(2)
                  << std::setw(13) << r.p95StepMs;
        if (showFps)
            std::cout << std::setprecision(1)
                      << std::setw(11) << r.meanFPS
                      << std::setw(10) << r.maxFPS
                      << std::setw(10) << r.p95FPS;
        std::cout << std::setw(7) << (r.rtfOk ? "YES" : "no") << "\n";
    }

    int maxOk = 0;
    for (auto& r : history) if (r.rtfOk) maxOk = std::max(maxOk, r.agents);

    if (proto.rtfThreshold > 0.0)
        std::cout << "\n  → Max agents with RTF ≥ " << proto.rtfThreshold
                  << ": " << maxOk << "\n";
    std::cout << "══════════════════════════════════════════════════════════════════\n\n";
}

// ─── main ─────────────────────────────────────────────────────────────────────

int main(int argc, const char* argv[])
{
    std::string selfExePath = (argc > 0) ? argv[0] : "./Benchmark";
    {
        char buf[4096] = {};
        if (realpath(selfExePath.c_str(), buf)) selfExePath = buf;
    }

    Args args;
    try { args = parseArgs(argc, argv); }
    catch (const std::exception& e)
    {
        std::cerr << "[ERROR] " << e.what() << "\n\n";
        printUsage(argv[0]);
        return 1;
    }

    // ── Child-run mode ────────────────────────────────────────────────────────
    // Children receive a pre-resolved --steps value and do NOT install a
    // signal handler — they use the default SIGINT behaviour (terminate and
    // let their CSVLogger destructor flush the temp file).
    if (args.childRun)
    {
        if (args.childCsv.empty())
        {
            std::cerr << "[ERROR] --child-run requires --child-csv\n";
            return 1;
        }
        std::string dataDirPath(DATA_DIR_PATH);
        std::filesystem::create_directories(args.output_dir);

        ProtocolConfig proto;
        try { proto = makeProtocol(args.protocol); }
        catch (const std::exception& e) { std::cerr << e.what() << "\n"; return 1; }
        proto = withTargetRTF(proto, args.targetRTFOverride);

        {
            CSVLogger logger(args.childCsv);
            try
            {
                runOnce(proto, args.agents, dataDirPath, args.warmup, args.steps, logger);
            }
            catch (const std::exception& e)
            {
                std::cerr << "[Child ERROR] " << e.what() << "\n";
                _exit(1);
            }
        }
        _exit(0);
    }

    // ── Parent / orchestrator mode ────────────────────────────────────────────

    try
    {
        if (!args.config_path.empty())
            loadConfigFile(args.config_path, args);
    }
    catch (const std::exception& e)
    {
        std::cerr << "[ERROR] " << e.what() << "\n";
        return 1;
    }

    if (args.agentStep <= 0)
    { std::cerr << "[ERROR] --agent-step must be > 0\n"; return 1; }
    if (args.minAgents <= 0 || args.maxAgents <= 0 || args.agents <= 0)
    { std::cerr << "[ERROR] agent counts must be > 0\n"; return 1; }
    if (args.minAgents > args.maxAgents)
    { std::cerr << "[ERROR] --min-agents must be <= --max-agents\n"; return 1; }

    std::string dataDirPath(DATA_DIR_PATH);
    std::filesystem::create_directories(args.output_dir);

    std::vector<ProtocolConfig> protocols;
    if (!args.configRuns.empty()) { /* filled below */ }
    else if (args.allProtocols)   { protocols = makeAllProtocols(); }
    else
    {
        try { protocols.push_back(withTargetRTF(makeProtocol(args.protocol), args.targetRTFOverride)); }
        catch (const std::exception& e) { std::cerr << "[ERROR] " << e.what() << "\n"; return 1; }
    }

    // ── Create summary logger and register signal handler ─────────────────────
    // Write-through in SummaryCSVLogger::write() means the file is always
    // current on disk. The signal handler therefore needs to do nothing more
    // than exit cleanly — the file is already complete up to the last run.
    SummaryCSVLogger summaryLogger(args.summary_csv);
    g_summaryLogger = &summaryLogger;
    std::signal(SIGINT,  parentSigHandler);
    std::signal(SIGTERM, parentSigHandler);

    // ── Print banner ──────────────────────────────────────────────────────────
    std::cout << "╔══════════════════════════════════════════════╗\n";
    std::cout << "║        Stonefish Benchmark Suite             ║\n";
    std::cout << "╚══════════════════════════════════════════════╝\n";
    if (!args.config_path.empty())
        std::cout << "  Config    : " << args.config_path << "\n";
    if (!args.configRuns.empty())
        std::cout << "  Protocols : from config runs\n";
    else if (args.allProtocols)
        std::cout << "  Protocols : A, B, C, D\n";
    else
        std::cout << "  Protocol  : " << protocols.front().name << "\n";
    std::cout << "  Warmup    : " << args.warmup << " steps\n";
    if (args.measureSeconds > 0.0)
        std::cout << "  Measure   : " << args.measureSeconds
                  << "s (resolved to steps per protocol)\n";
    else
        std::cout << "  Measure   : " << args.steps << " steps\n";
    std::cout << "  Summary   : " << args.summary_csv << "\n";
    std::cout << "  Output dir: " << args.output_dir << "\n\n";

    // Helper: resolve steps for a given protocol and launch child
    auto runAndRecord = [&](const ProtocolConfig& proto, int agents) -> RunResult
    {
        int resolvedSteps = resolveSteps(proto, args.measureSeconds, args.steps);
        return runInSubprocess(proto, agents, dataDirPath,
                               args.warmup, resolvedSteps,
                               args.output_dir, summaryLogger, selfExePath);
    };

    // ── Config-file runs ──────────────────────────────────────────────────────
    if (!args.configRuns.empty())
    {
        for (const auto& configRun : args.configRuns)
        {
            const ProtocolConfig proto =
                withTargetRTF(makeProtocol(configRun.protocol), configRun.targetRTF);
            int resolvedSteps = resolveSteps(proto, args.measureSeconds, args.steps);
            std::cout << "[Benchmark] Config run for protocol " << proto.name
                      << "  target_rtf=" << proto.targetRTF
                      << "  measure_steps=" << resolvedSteps << "\n";

            std::vector<RunResult> history;
            for (int agents : configRun.agents)
            {
                RunResult r = runAndRecord(proto, agents);
                history.push_back(r);
                printResult(r, proto);
                std::this_thread::sleep_for(std::chrono::milliseconds(200));
            }
            if (!history.empty()) printSummary(history, proto);
        }
        std::cout << "[Done] Summary: " << args.summary_csv << "\n";
        g_summaryLogger = nullptr;
        return 0;
    }

    // ── Single run ────────────────────────────────────────────────────────────
    if (!args.search && !args.autoSweep && !args.allProtocols)
    {
        const ProtocolConfig& proto = protocols.front();
        std::cout << "[Benchmark] Single run: " << args.agents << " agents\n";
        RunResult r = runAndRecord(proto, args.agents);
        printSummary({r}, proto);
        std::cout << "[Done] Summary: " << args.summary_csv << "\n";
        g_summaryLogger = nullptr;
        return 0;
    }

    // ── Sweep / search / all-protocols ────────────────────────────────────────
    for (const auto& proto : protocols)
    {
        std::vector<RunResult> history;

        if (args.autoSweep)
        {
            std::cout << "[Benchmark] Auto sweep: protocol " << proto.name
                      << "  " << args.minAgents << "–" << args.maxAgents
                      << " agents, step " << args.agentStep << "\n\n";

            for (int n = args.minAgents; n <= args.maxAgents; n += args.agentStep)
            {
                RunResult r = runAndRecord(proto, n);
                history.push_back(r);
                printResult(r, proto);
                if (!r.rtfOk)
                {
                    std::cout << "  Stopping: real-time no longer maintained.\n";
                    break;
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(200));
            }
        }
        else if (args.search)
        {
            if (proto.rtfThreshold > 0.0)
            {
                std::cout << "[Benchmark] Binary search: "
                          << args.minAgents << "–" << args.maxAgents << " agents\n\n";

                RunResult upper = runAndRecord(proto, args.maxAgents);
                history.push_back(upper);
                printResult(upper, proto);

                if (!upper.rtfOk)
                {
                    int lo = args.minAgents, hi = args.maxAgents - 1;
                    while (lo <= hi)
                    {
                        int mid = lo + (hi - lo) / 2;
                        RunResult r = runAndRecord(proto, mid);
                        history.push_back(r);
                        printResult(r, proto);
                        if (r.rtfOk) lo = mid + 1;
                        else         hi = mid - 1;
                    }
                }
                else
                {
                    std::cout << "\n  → Even max (" << args.maxAgents
                              << " agents) passes. Increase --max-agents.\n";
                }
            }
            else
            {
                std::cout << "[Benchmark] Exponential sweep (uncapped protocol)\n\n";
                for (int n = args.minAgents; n <= args.maxAgents; n *= 2)
                {
                    RunResult r = runAndRecord(proto, n);
                    history.push_back(r);
                    printResult(r, proto);
                    if (n > args.maxAgents / 2) break;
                }
                if (args.maxAgents > 1 && (args.maxAgents & (args.maxAgents - 1)) != 0)
                {
                    RunResult r = runAndRecord(proto, args.maxAgents);
                    history.push_back(r);
                    printResult(r, proto);
                }
            }
        }
        else if (args.allProtocols)
        {
            std::cout << "[Benchmark] Single run: protocol " << proto.name
                      << "  " << args.agents << " agents\n";
            RunResult r = runAndRecord(proto, args.agents);
            history.push_back(r);
        }

        if (!history.empty()) printSummary(history, proto);
    }

    std::cout << "[Done] Summary: " << args.summary_csv << "\n";
    g_summaryLogger = nullptr;
    return 0;
}

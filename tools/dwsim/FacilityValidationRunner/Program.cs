using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;

namespace FacilityValidationRunner
{
    internal static class Program
    {
        internal static string DwsimHome { get; private set; }

        [STAThread]
        private static int Main(string[] args)
        {
            try
            {
                var parsed = Arguments.Parse(args);
                DwsimHome = Path.GetFullPath(
                    parsed.GetOptional("dwsim-home")
                    ?? Environment.GetEnvironmentVariable("DWSIM_HOME")
                    ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DWSIM"));
                if (!File.Exists(Path.Combine(DwsimHome, "DWSIM.Automation.dll")))
                {
                    throw new DirectoryNotFoundException("DWSIM_HOME is not a DWSIM installation: " + DwsimHome);
                }
                AppDomain.CurrentDomain.AssemblyResolve += ResolveFromDwsimHome;
                return Runner.Run(parsed);
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.ToString());
                return 1;
            }
        }

        private static Assembly ResolveFromDwsimHome(object sender, ResolveEventArgs args)
        {
            var name = new AssemblyName(args.Name).Name + ".dll";
            foreach (var directory in new[] { "", "ThermoCS", "unitops", "ppacks", "plugins", "extenders" })
            {
                var candidate = Path.Combine(DwsimHome, directory, name);
                if (File.Exists(candidate))
                {
                    return Assembly.LoadFrom(candidate);
                }
            }
            return null;
        }
    }

    internal sealed class Arguments
    {
        private readonly Dictionary<string, string> _values;

        private Arguments(Dictionary<string, string> values)
        {
            _values = values;
        }

        internal static Arguments Parse(string[] args)
        {
            var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            for (var index = 0; index < args.Length; index++)
            {
                if (!args[index].StartsWith("--", StringComparison.Ordinal))
                {
                    throw new ArgumentException("Unexpected argument: " + args[index]);
                }
                var key = args[index].Substring(2);
                if (key == "create-model")
                {
                    values[key] = "true";
                    continue;
                }
                if (++index >= args.Length)
                {
                    throw new ArgumentException("Missing value for --" + key);
                }
                values[key] = args[index];
            }
            return new Arguments(values);
        }

        internal bool Has(string key)
        {
            return _values.ContainsKey(key);
        }

        internal string GetRequired(string key)
        {
            string value;
            if (!_values.TryGetValue(key, out value) || string.IsNullOrWhiteSpace(value))
            {
                throw new ArgumentException("Missing required argument --" + key);
            }
            return Path.GetFullPath(value);
        }

        internal string GetOptional(string key)
        {
            string value;
            return _values.TryGetValue(key, out value) ? value : null;
        }
    }

    internal static class Runner
    {
        private const double SecondsPerDay = 86400.0;

        internal static int Run(Arguments args)
        {
            var modelPath = args.GetRequired("model");
            var casesPath = args.GetRequired("cases");
            var outputPath = args.GetRequired("output");
            if (!File.Exists(casesPath))
            {
                throw new FileNotFoundException("Validation cases were not found.", casesPath);
            }
            Directory.CreateDirectory(Path.GetDirectoryName(modelPath));
            Directory.CreateDirectory(Path.GetDirectoryName(outputPath));

            var caseDocument = Newtonsoft.Json.Linq.JObject.Parse(File.ReadAllText(casesPath));
            var cases = (Newtonsoft.Json.Linq.JArray)caseDocument["cases"];
            if (cases == null || cases.Count != 8)
            {
                throw new InvalidDataException("Feature 003 requires exactly eight validation cases.");
            }

            var originalDirectory = Environment.CurrentDirectory;
            Environment.CurrentDirectory = Program.DwsimHome;
            try
            {
                var automation = new DWSIM.Automation.Automation3();
                if (args.Has("create-model"))
                {
                    CreateModel(automation, modelPath, caseDocument);
                }
                if (!File.Exists(modelPath))
                {
                    throw new FileNotFoundException("DWSIM model was not found; run once with --create-model.", modelPath);
                }
                var rows = ExecuteCases(automation, modelPath, casesPath, caseDocument);
                WriteCsv(outputPath, rows);
                automation.ReleaseResources();
                if (rows.Any(row => !row.Converged))
                {
                    return 2;
                }
                return 0;
            }
            finally
            {
                Environment.CurrentDirectory = originalDirectory;
            }
        }

        private static void CreateModel(
            DWSIM.Automation.Automation3 automation,
            string modelPath,
            Newtonsoft.Json.Linq.JObject document)
        {
            var sim = automation.CreateFlowsheet();
            sim.AddCompound("Carbon dioxide");
            var propertyPackage = sim.CreateAndAddPropertyPackage("CoolProp");

            var productionFeed = AddStream(sim, propertyPackage, "PROD-FEED", "Produced fluid CO2 equivalent", 40, 120);
            var separatorGas = AddStream(sim, propertyPackage, "SEP-GAS", "Separator recovered CO2", 220, 80);
            var separatorOil = AddStream(sim, propertyPackage, "SEP-OIL", "Separator oil boundary", 220, 130);
            var separatorWater = AddStream(sim, propertyPackage, "SEP-WATER", "Separator water boundary", 220, 180);
            var dehydrated = AddStream(sim, propertyPackage, "DEHY-OUT", "Dehydrated recycle CO2", 390, 80);
            var compressor1Out = AddStream(sim, propertyPackage, "C1-OUT", "Compressor stage 1 outlet", 540, 80);
            var intercooler1Out = AddStream(sim, propertyPackage, "IC1-OUT", "Intercooler stage 1 outlet", 680, 80);
            var compressor2Out = AddStream(sim, propertyPackage, "C2-OUT", "Compressor stage 2 outlet", 820, 80);
            var intercooler2Out = AddStream(sim, propertyPackage, "IC2-OUT", "Intercooler stage 2 outlet", 960, 80);
            var compressor3Out = AddStream(sim, propertyPackage, "C3-OUT", "Compressor stage 3 outlet", 1100, 80);
            var recycleDense = AddStream(sim, propertyPackage, "RECYCLE-DENSE", "Dense recovered recycle CO2", 1240, 80);
            var freshDense = AddStream(sim, propertyPackage, "FRESH-DENSE", "Feature 002 dense fresh CO2 delivery", 1100, 250);
            var pumpSuction = AddStream(sim, propertyPackage, "PUMP-SUCTION", "Combined fresh and recycle CO2", 1390, 160);
            var injectionOutlet = AddStream(sim, propertyPackage, "INJECTION-OUT", "Wellhead injection CO2", 1660, 160);

            var separator = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Vessel, 140, 120, "SEP-01", "SEP-01");
            var dehydration = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Heater, 310, 80, "DEHY-01", "DEHY-01");
            var compressor1 = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Compressor, 470, 80, "COMP-01", "COMP-01");
            var cooler1 = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Cooler, 610, 80, "COOL-01", "COOL-01");
            var compressor2 = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Compressor, 750, 80, "COMP-02", "COMP-02");
            var cooler2 = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Cooler, 890, 80, "COOL-02", "COOL-02");
            var compressor3 = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Compressor, 1030, 80, "COMP-03", "COMP-03");
            var cooler3 = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Cooler, 1170, 80, "COOL-03", "COOL-03");
            var mixer = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Mixer, 1320, 160, "MIX-01", "MIX-01");
            var pump = sim.AddObject(DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.Pump, 1530, 160, "PUMP-01", "PUMP-01");

            Connect(sim, productionFeed, separator, 0, 0);
            Connect(sim, separator, separatorGas, 0, 0);
            Connect(sim, separator, separatorOil, 1, 0);
            Connect(sim, separator, separatorWater, 2, 0);
            Connect(sim, separatorGas, dehydration, 0, 0);
            Connect(sim, dehydration, dehydrated, 0, 0);
            Connect(sim, dehydrated, compressor1, 0, 0);
            Connect(sim, compressor1, compressor1Out, 0, 0);
            Connect(sim, compressor1Out, cooler1, 0, 0);
            Connect(sim, cooler1, intercooler1Out, 0, 0);
            Connect(sim, intercooler1Out, compressor2, 0, 0);
            Connect(sim, compressor2, compressor2Out, 0, 0);
            Connect(sim, compressor2Out, cooler2, 0, 0);
            Connect(sim, cooler2, intercooler2Out, 0, 0);
            Connect(sim, intercooler2Out, compressor3, 0, 0);
            Connect(sim, compressor3, compressor3Out, 0, 0);
            Connect(sim, compressor3Out, cooler3, 0, 0);
            Connect(sim, cooler3, recycleDense, 0, 0);
            Connect(sim, freshDense, mixer, 0, 0);
            Connect(sim, recycleDense, mixer, 0, 1);
            Connect(sim, mixer, pumpSuction, 0, 0);
            Connect(sim, pumpSuction, pump, 0, 0);
            Connect(sim, pump, injectionOutlet, 0, 0);

            ApplyCase(sim, (Newtonsoft.Json.Linq.JObject)((Newtonsoft.Json.Linq.JArray)document["cases"])[0], (Newtonsoft.Json.Linq.JObject)document["fixed"]);
            var errors = automation.CalculateFlowsheet4(sim);
            if (errors.Count > 0)
            {
                throw new InvalidOperationException("Baseline DWSIM model did not converge: " + string.Join(" | ", errors.Select(error => error.Message)));
            }
            automation.SaveFlowsheet(sim, modelPath, true);
        }

        private static List<ReferenceRow> ExecuteCases(
            DWSIM.Automation.Automation3 automation,
            string modelPath,
            string casesPath,
            Newtonsoft.Json.Linq.JObject document)
        {
            var modelHash = Sha256(modelPath);
            var casesHash = Sha256(casesPath);
            var version = FileVersionInfo.GetVersionInfo(Path.Combine(Program.DwsimHome, "DWSIM.exe")).FileVersion;
            var fixedValues = (Newtonsoft.Json.Linq.JObject)document["fixed"];
            var rows = new List<ReferenceRow>();
            foreach (Newtonsoft.Json.Linq.JObject validationCase in (Newtonsoft.Json.Linq.JArray)document["cases"])
            {
                var sim = automation.LoadFlowsheet(modelPath);
                ApplyCase(sim, validationCase, fixedValues);
                var errors = automation.CalculateFlowsheet4(sim);
                var converged = errors.Count == 0 && sim.Solved;
                var compressorPower = SumCompressorHeatDuty(sim, "COMP-01", "COMP-02", "COMP-03");
                var coolingDuty = SumCoolerHeatDuty(sim, "COOL-01", "COOL-02", "COOL-03");
                var pump = (DWSIM.UnitOperations.UnitOperations.Pump)sim.GetFlowsheetSimulationObject("PUMP-01");
                var productionFeed = (DWSIM.Interfaces.IMaterialStream)sim.GetFlowsheetSimulationObject("PROD-FEED");
                var freshFeed = (DWSIM.Interfaces.IMaterialStream)sim.GetFlowsheetSimulationObject("FRESH-DENSE");
                var injectionOutlet = (DWSIM.Interfaces.IMaterialStream)sim.GetFlowsheetSimulationObject("INJECTION-OUT");
                var inletMass = productionFeed.GetMassFlow() + freshFeed.GetMassFlow();
                var outletMass = injectionOutlet.GetMassFlow();
                var residual = Math.Abs(inletMass - outletMass) / Math.Max(inletMass, 1e-12);
                rows.Add(new ReferenceRow
                {
                    CaseId = (string)validationCase["case_id"],
                    Converged = converged,
                    DwsimVersion = version,
                    ModelSha256 = modelHash,
                    CasesSha256 = casesHash,
                    PropertyPackage = "CoolProp",
                    CompressorPowerKw = compressorPower,
                    PumpPowerKw = pump.HeatDuty,
                    TotalPowerKw = compressorPower + pump.HeatDuty,
                    CoolingDutyKw = coolingDuty,
                    SeparatorGasStdM3Day = (double)validationCase["peak_produced_gas_std_m3_day"],
                    InletMassKgS = inletMass,
                    OutletMassKgS = outletMass,
                    MassBalanceResidualFraction = residual,
                    ErrorMessage = string.Join(" | ", errors.Select(error => error.Message))
                });
            }
            return rows;
        }

        private static void ApplyCase(
            DWSIM.Interfaces.IFlowsheet sim,
            Newtonsoft.Json.Linq.JObject validationCase,
            Newtonsoft.Json.Linq.JObject fixedValues)
        {
            var referencePressure = (double)fixedValues["injection_reference_pressure_bar"] * 100000.0;
            var referenceTemperature = (double)fixedValues["injection_reference_temperature_c"] + 273.15;
            var standardDensity = CoolProp.PropsSI("D", "T", referenceTemperature, "P", referencePressure, "CO2");
            var freshMass = (double)validationCase["injection_rate_std_m3_day"] / SecondsPerDay * standardDensity;
            var producedMass = (double)validationCase["peak_produced_gas_std_m3_day"]
                * (double)validationCase["produced_co2_mole_fraction"]
                / SecondsPerDay
                * standardDensity;
            var recoveredMass = producedMass * (double)fixedValues["recycle_recovery_fraction"];
            var separatorPressure = (double)fixedValues["separator_pressure_bar"] * 100000.0;
            var separatorTemperature = (double)fixedValues["separator_temperature_c"] + 273.15;
            var deliveryPressureBar = (double)validationCase["delivery_pressure_bar"];
            var deliveryPressure = deliveryPressureBar * 100000.0;
            var deliveryTemperature = (double)fixedValues["delivery_temperature_c"] + 273.15;
            var wellheadPressure = (double)fixedValues["wellhead_injection_pressure_bar"] * 100000.0;

            SetFeed((DWSIM.Interfaces.IMaterialStream)sim.GetFlowsheetSimulationObject("PROD-FEED"), recoveredMass, separatorPressure, separatorTemperature);
            SetFeed((DWSIM.Interfaces.IMaterialStream)sim.GetFlowsheetSimulationObject("FRESH-DENSE"), freshMass, deliveryPressure, deliveryTemperature);

            var ratio = Math.Pow(deliveryPressure / separatorPressure, 1.0 / 3.0);
            var pressureDrop = 25000.0;
            var compressors = new[] { "COMP-01", "COMP-02", "COMP-03" };
            var coolers = new[] { "COOL-01", "COOL-02", "COOL-03" };
            for (var stage = 0; stage < compressors.Length; stage++)
            {
                var targetPressure = separatorPressure * Math.Pow(ratio, stage + 1);
                var compressor = (DWSIM.UnitOperations.UnitOperations.Compressor)sim.GetFlowsheetSimulationObject(compressors[stage]);
                compressor.CalcMode = DWSIM.UnitOperations.UnitOperations.Compressor.CalculationMode.OutletPressure;
                compressor.POut = targetPressure + (stage < 2 ? pressureDrop : 0.0);
                compressor.AdiabaticEfficiency = 75.0;
                compressor.ProcessPath = DWSIM.UnitOperations.UnitOperations.Compressor.ProcessPathType.Adiabatic;
                var cooler = (DWSIM.UnitOperations.UnitOperations.Cooler)sim.GetFlowsheetSimulationObject(coolers[stage]);
                cooler.CalcMode = DWSIM.UnitOperations.UnitOperations.Cooler.CalculationMode.OutletTemperature;
                cooler.OutletTemperature = (stage < 2 ? 35.0 : (double)fixedValues["delivery_temperature_c"]) + 273.15;
                cooler.DeltaP = stage < 2 ? pressureDrop : 0.0;
            }
            var dehydration = (DWSIM.UnitOperations.UnitOperations.Heater)sim.GetFlowsheetSimulationObject("DEHY-01");
            dehydration.CalcMode = DWSIM.UnitOperations.UnitOperations.Heater.CalculationMode.OutletTemperature;
            dehydration.OutletTemperature = separatorTemperature;
            dehydration.DeltaP = 0.0;
            var pump = (DWSIM.UnitOperations.UnitOperations.Pump)sim.GetFlowsheetSimulationObject("PUMP-01");
            pump.CalcMode = DWSIM.UnitOperations.UnitOperations.Pump.CalculationMode.OutletPressure;
            pump.Pout = wellheadPressure;
            pump.Efficiency = 78.0;
            pump.IgnorePhase = true;
        }

        private static DWSIM.Interfaces.IMaterialStream AddStream(
            DWSIM.Interfaces.IFlowsheet sim,
            DWSIM.Interfaces.IPropertyPackage propertyPackage,
            string id,
            string tag,
            int x,
            int y)
        {
            var stream = (DWSIM.Interfaces.IMaterialStream)sim.AddObject(
                DWSIM.Interfaces.Enums.GraphicObjects.ObjectType.MaterialStream,
                x,
                y,
                id,
                id);
            stream.SetPropertyPackageObject(propertyPackage);
            stream.SetOverallComposition(new[] { 1.0 });
            return stream;
        }

        private static void SetFeed(DWSIM.Interfaces.IMaterialStream stream, double massFlow, double pressure, double temperature)
        {
            stream.SetOverallComposition(new[] { 1.0 });
            stream.SetMassFlow(massFlow);
            stream.SetPressure(pressure);
            stream.SetTemperature(temperature);
        }

        private static void Connect(
            DWSIM.Interfaces.IFlowsheet sim,
            object source,
            object destination,
            int sourceIndex,
            int destinationIndex)
        {
            var from = (DWSIM.Interfaces.ISimulationObject)source;
            var to = (DWSIM.Interfaces.ISimulationObject)destination;
            sim.ConnectObjects(from.GraphicObject, to.GraphicObject, sourceIndex, destinationIndex);
        }

        private static double SumCompressorHeatDuty(DWSIM.Interfaces.IFlowsheet sim, params string[] ids)
        {
            return ids.Sum(id => ((DWSIM.UnitOperations.UnitOperations.Compressor)sim.GetFlowsheetSimulationObject(id)).HeatDuty);
        }

        private static double SumCoolerHeatDuty(DWSIM.Interfaces.IFlowsheet sim, params string[] ids)
        {
            return ids.Sum(id => ((DWSIM.UnitOperations.UnitOperations.Cooler)sim.GetFlowsheetSimulationObject(id)).HeatDuty);
        }

        private static string Sha256(string path)
        {
            using (var algorithm = SHA256.Create())
            using (var stream = File.OpenRead(path))
            {
                return string.Concat(algorithm.ComputeHash(stream).Select(value => value.ToString("x2", CultureInfo.InvariantCulture)));
            }
        }

        private static void WriteCsv(string path, List<ReferenceRow> rows)
        {
            var culture = CultureInfo.InvariantCulture;
            using (var writer = new StreamWriter(path, false, new UTF8Encoding(false)))
            {
                writer.WriteLine("case_id,converged,dwsim_version,model_sha256,cases_sha256,property_package,compressor_power_kw,pump_power_kw,total_power_kw,cooling_duty_kw,separator_gas_std_m3_day,inlet_mass_kg_s,outlet_mass_kg_s,mass_balance_residual_fraction,error_message");
                foreach (var row in rows)
                {
                    writer.WriteLine(string.Join(",", new[]
                    {
                        Csv(row.CaseId),
                        row.Converged ? "true" : "false",
                        Csv(row.DwsimVersion),
                        row.ModelSha256,
                        row.CasesSha256,
                        row.PropertyPackage,
                        row.CompressorPowerKw.ToString("G17", culture),
                        row.PumpPowerKw.ToString("G17", culture),
                        row.TotalPowerKw.ToString("G17", culture),
                        row.CoolingDutyKw.ToString("G17", culture),
                        row.SeparatorGasStdM3Day.ToString("G17", culture),
                        row.InletMassKgS.ToString("G17", culture),
                        row.OutletMassKgS.ToString("G17", culture),
                        row.MassBalanceResidualFraction.ToString("G17", culture),
                        Csv(row.ErrorMessage)
                    }));
                }
            }
        }

        private static string Csv(string value)
        {
            value = value ?? string.Empty;
            return value.IndexOfAny(new[] { ',', '"', '\r', '\n' }) >= 0
                ? "\"" + value.Replace("\"", "\"\"") + "\""
                : value;
        }
    }

    internal sealed class ReferenceRow
    {
        internal string CaseId;
        internal bool Converged;
        internal string DwsimVersion;
        internal string ModelSha256;
        internal string CasesSha256;
        internal string PropertyPackage;
        internal double CompressorPowerKw;
        internal double PumpPowerKw;
        internal double TotalPowerKw;
        internal double CoolingDutyKw;
        internal double SeparatorGasStdM3Day;
        internal double InletMassKgS;
        internal double OutletMassKgS;
        internal double MassBalanceResidualFraction;
        internal string ErrorMessage;
    }
}

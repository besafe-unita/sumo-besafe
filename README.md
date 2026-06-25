# Sumo-based evaluation of different cyclist profiles

Minimal SUMO scenario for quickly reproducing and comparing mixed car/bicycle traffic at a controlled four-arm intersection, with configurable cyclist behaviour profiles.

## Requirements

- Python 3
- Eclipse SUMO, with `sumo`, `sumo-gui` and `netconvert` available in `PATH`

Check the SUMO installation with:

```bash
sumo --version
sumo-gui --version
```

## Project layout

- `bin/gendemand.py`: deterministic demand generator for the four-arm intersection.
- `sumocfg/intersection.net.xml`: SUMO network used by the generated scenarios.
- `sumocfg/vtypes.add.xml`: vehicle type definitions for cars and the two cyclist profiles.
- `sumocfg/gendemand.sh`: convenience script that generates three cyclist-profile variants for the same traffic volume.
- `results/`: suggested output directory for simulation results.

## Generate a SUMO demand file

Use `bin/gendemand.py` to generate one route file under `sumocfg/`.

```bash
python3 bin/gendemand.py \
  --carpm 5 \
  --bikepm 3 \
  --safefraction 0.7 \
  --outname car5vpm_bike3vpm_safe70risky30.rou.xml
```

Parameters:

- `--carpm`: cars per minute injected from each arm of the intersection.
- `--bikepm`: bicycles per minute injected from each arm of the intersection.
- `--safefraction`: fraction of bicycles using the `bike_safety_oriented` profile. Use `1.0` for all safety-oriented cyclists, `0.0` for all high-risk cyclists, or an intermediate value such as `0.7`.
- `--outname`: output route filename or base name. The file is written to `sumocfg/`; the `.rou.xml` suffix is added automatically if omitted.

The generator creates a deterministic one-hour demand (`0` to `3600` seconds). Vehicles enter from the four approaches (`N`, `E`, `S`, `W`) and cycle through straight, right-turn, straight and left-turn movements.

## Generate four custom scenarios

Use `sumocfg/gendemand.sh` to generate four route files for the same traffic volumes:

- `*_safety.rou.xml`: all bicycles use `bike_safety_oriented`.
- `*_risky.rou.xml`: all bicycles use `bike_high_risk`.
- `*_safe70risky30.rou.xml`: 70% safety-oriented bicycles and 30% high-risk bicycles.
- `*_autoonly.rou.xml`: car-only baseline with the same car demand and no bicycles.

Example with `5` cars/minute and `3` bicycles/minute from each arm:

```bash
./sumocfg/gendemand.sh 5 3
```

This writes:

```text
sumocfg/car5vpm_bike3vpm_safety.rou.xml
sumocfg/car5vpm_bike3vpm_risky.rou.xml
sumocfg/car5vpm_bike3vpm_safe70risky30.rou.xml
sumocfg/car5vpm_bike3vpm_autoonly.rou.xml
```

If no arguments are provided, the script uses `5` cars/minute and `3` bicycles/minute by default:

```bash
./sumocfg/gendemand.sh
```

## Run a scenario with SUMO GUI

To inspect one generated route file in `sumo-gui`, launch SUMO with the network, route file and vehicle-type definitions:

```bash
cd sumocfg
sumo-gui \
  -n intersection.net.xml \
  -r car5vpm_bike3vpm_safe70risky30.rou.xml \
  -a vtypes.add.xml \
  --begin 0 \
  --end 3600 \
  --step-length 0.1 \
  --lateral-resolution 0.8 \
  --collision.check-junctions true
```

You can replace `car5vpm_bike3vpm_safe70risky30.rou.xml` with any generated route file, for example `car5vpm_bike3vpm_safety.rou.xml` or `car5vpm_bike3vpm_risky.rou.xml`.

Existing `.sumocfg` files can also be opened directly:

```bash
sumo-gui -c sumocfg/car5vpm_bike3vpm_safe70risky30.sumocfg
```

## Run from the command line and save outputs

For batch runs, use `sumo` and write the outputs to `results/`:

```bash
sumo \
  -n sumocfg/intersection.net.xml \
  -r sumocfg/car5vpm_bike3vpm_safe70risky30.rou.xml \
  -a sumocfg/vtypes.add.xml \
  --begin 0 \
  --end 3600 \
  --step-length 0.1 \
  --lateral-resolution 0.8 \
  --collision.check-junctions true \
  --tripinfo-output results/car5vpm_bike3vpm_safe70risky30_tripinfo.csv \
  --statistic-output results/car5vpm_bike3vpm_safe70risky30_stats.xml \
  --summary-output results/car5vpm_bike3vpm_safe70risky30_summary.csv
```

The checked-in `.sumocfg` files also write `collision-output`; the three bicycle
scenarios additionally write SSM outputs (`*_ssm.xml`) with TTC, DRAC and PET
enabled.

## Analyze outputs

Run the standard tripinfo/statistics comparison:

```bash
python3 analysis/compare_scenarios.py
```

Run the SSM-specific analysis:

```bash
python3 analysis/analyze_ssm.py
```

The analysis scripts write report-ready PDF figures and CSV tables under
`analysis/plots/`. The SSM plot focuses on crossing conflicts involving
bicycles, keeping longitudinal following conflicts separate from the safety
message.

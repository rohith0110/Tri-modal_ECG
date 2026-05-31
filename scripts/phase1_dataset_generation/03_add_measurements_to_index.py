import pandas as pd

INDEX_PATH = "../processed/index/index_clean.parquet"
MEAS_PATH = "../data/machine_measurements.csv"

OUT_PATH = "../processed/index/index_clean_with_measurements.parquet"

print("Loading index...")
df = pd.read_parquet(INDEX_PATH)

print("Loading machine measurements...")

meas = pd.read_csv(
    MEAS_PATH,
    usecols=[
        "study_id",
        "rr_interval",
        "p_onset",
        "p_end",
        "qrs_onset",
        "qrs_end",
        "t_end",
        "p_axis",
        "qrs_axis",
        "t_axis",
    ],
    low_memory=False,
)

print("Merging measurements into index...")

df = df.merge(meas, on="study_id", how="left")

print("Saving new index...")

df.to_parquet(OUT_PATH)

print("\nDone.")
print("New columns:")
print(df.columns)
print("Rows:", len(df))

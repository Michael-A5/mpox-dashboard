import preprocessing

SOURCE_CSV = r"C:\Users\user\Desktop\Data\mpox_synthetic_line_list_final.csv"  # change to where you saved it

clean_df, quality_report = preprocessing.preprocess(SOURCE_CSV)
clean_df.to_parquet("data/demo_line_list.parquet", index=False)
print(len(clean_df), "rows written")
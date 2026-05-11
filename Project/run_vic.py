from vic_framework import vic_batch

charts = [
    "chart01.png", "chart02.png", "chart03.png",
    "chart04.png", "chart05.png", "chart06.png",
    "chart07.png", "chart08.png", "chart09.png",
    "chart10.png", "chart11.png", "chart12.png",
]

vic_batch(charts, output_csv="vic_results.csv")

#!/bin/bash

# Example commands for cheshire

source venv/bin/activate

echo "Basic bar chart:"
echo "cheshire \"SELECT sum(sales) as y, region as x FROM sales_table GROUP BY region\" bar 0"
echo

echo "Grouped bar chart (products by region):"
echo "cheshire \"SELECT region as x, sum(sales) as y, product as color FROM sales_table GROUP BY region, product\" bar 0"
echo

echo "Line chart over time:"
echo "cheshire \"SELECT date as x, sum(sales) as y FROM sales_table GROUP BY date ORDER BY date\" line 0"
echo

echo "Multi-line chart (sales by region over time):"
echo "cheshire \"SELECT date as x, sum(sales) as y, region as color FROM sales_table GROUP BY date, region ORDER BY date\" line 0"
echo

echo "Scatter plot:"
echo "cheshire \"SELECT rowid as x, sales as y, region as color FROM sales_table\" scatter 0"
echo

echo "Histogram of sales distribution:"
echo "cheshire \"SELECT null as x, sales as y FROM sales_table\" histogram 0"
echo

echo "With refresh (updates every 5 seconds):"
echo "cheshire \"SELECT sum(sales) as y, region as x FROM sales_table GROUP BY region\" bar 5s"
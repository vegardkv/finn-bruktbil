# Car Price Model Analysis

This document describes the OLS (Ordinary Least Squares) regression model implementation for analyzing car prices based on mileage and age.

## Model Description

The implemented model follows the formula:
```
Price = c₀ + c₁ × Mileage + c₂ × Age
```

Where:
- `c₀` is the intercept (base price when mileage and age are zero)
- `c₁` is the coefficient for mileage (NOK per kilometer)
- `c₂` is the coefficient for age (NOK per year)

## Features

### 1. OLS Regression Analysis
- **Model Fitting**: Uses scikit-learn's LinearRegression for optimal performance, with fallback to manual implementation
- **Accuracy Metrics**: Reports R², Mean Absolute Error (MAE), and Root Mean Square Error (RMSE)
- **Coefficient Interpretation**: Clear explanation of how mileage and age affect car prices

### 2. Usedness Score
After fitting the model, a combined "usedness" metric is calculated:
```
usedness = (|c₁| × normalized_mileage + |c₂| × normalized_age) / (|c₁| + |c₂|)
```

This creates a 0-1 scale where:
- `0` represents a new car (zero mileage and age)
- `1` represents maximum usedness based on the data

### 3. Visualizations
- **Price vs. Usedness Plot**: Scatter plot showing the relationship between the combined usedness score and price
- **Original Plots**: Enhanced existing mileage and registration date plots
- **Correlation Analysis**: Statistical correlation between usedness and price

### 4. Enhanced Data Display
- The results table now includes the usedness score for each car (when analysis is successful)
- Cars are sorted by price for easy comparison

## Usage

1. **Install Dependencies**: 
   ```bash
   uv add scikit-learn numpy
   ```

2. **Run Analysis**: 
   Start the Streamlit app and the OLS analysis will automatically run on the filtered data:
   ```bash
   streamlit run finnbruktbil/analysis_app.py
   ```

3. **Interpret Results**:
   - **R² Score**: Higher values (closer to 1.0) indicate better model fit
   - **MAE/RMSE**: Lower values indicate more accurate predictions
   - **Coefficients**: Show the depreciation per kilometer and per year
   - **Usedness Score**: Allows comparing cars across different mileage/age combinations

## Requirements

- **Minimum Data**: At least 10 cars with complete price, mileage, and age data
- **Dependencies**: 
  - `scikit-learn >= 1.0` (recommended)
  - `numpy >= 1.20`
  - `pandas`
  - `streamlit`
  - `plotly`

## Model Limitations

1. **Linear Assumption**: Assumes linear relationship between price and predictors
2. **No Interaction Terms**: Doesn't account for interaction between mileage and age
3. **Missing Variables**: Doesn't include other important factors like brand, model, condition, etc.
4. **Outlier Sensitivity**: OLS is sensitive to outliers in the data

## Future Enhancements

- Add polynomial terms for non-linear relationships
- Include categorical variables (brand, model, fuel type)
- Implement robust regression techniques
- Add cross-validation for model evaluation
- Include confidence intervals for predictions
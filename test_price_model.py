#!/usr/bin/env python3
"""
Test script for the OLS price model implementation.
This creates synthetic data to validate the model functionality.
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

def test_ols_implementation():
    """Test the OLS implementation with synthetic data."""
    
    # Create synthetic car data
    np.random.seed(42)
    n_cars = 100
    
    # Generate realistic car data
    mileage = np.random.uniform(0, 300000, n_cars)  # 0-300k km
    age = np.random.uniform(0, 20, n_cars)  # 0-20 years
    
    # Create a realistic price model with some noise
    true_c0 = 400000  # Base price: 400k NOK
    true_c1 = -0.5    # -0.5 NOK per km
    true_c2 = -15000  # -15k NOK per year
    noise = np.random.normal(0, 20000, n_cars)  # 20k NOK noise
    
    price = true_c0 + true_c1 * mileage + true_c2 * age + noise
    price = np.maximum(price, 50000)  # Minimum price 50k NOK
    
    # Create DataFrame
    test_data = pd.DataFrame({
        'ad_id': [f'test_{i}' for i in range(n_cars)],
        'pris_eks_omreg': price,
        'kilometerstand_km': mileage,
        'age_years': age,
        'title': [f'Test Car {i}' for i in range(n_cars)],
        'merke': ['TestBrand'] * n_cars,
        'modell': ['TestModel'] * n_cars,
    })
    
    print("Test Data Summary:")
    print(f"Cars: {len(test_data)}")
    print(f"Price range: {test_data['pris_eks_omreg'].min():,.0f} - {test_data['pris_eks_omreg'].max():,.0f} NOK")
    print(f"Mileage range: {test_data['kilometerstand_km'].min():,.0f} - {test_data['kilometerstand_km'].max():,.0f} km")
    print(f"Age range: {test_data['age_years'].min():.1f} - {test_data['age_years'].max():.1f} years")
    print()
    
    # Import the OLS function
    try:
        # Try to import from the actual module
        from finnbruktbil.analysis_app import perform_ols_analysis
        print("✅ Successfully imported perform_ols_analysis function")
    except ImportError as e:
        print(f"❌ Failed to import perform_ols_analysis: {e}")
        return False
    
    # Test the OLS analysis
    try:
        model, analysis_subset, metrics, predictions = perform_ols_analysis(test_data)
        
        if metrics is None:
            print("❌ OLS analysis failed - no metrics returned")
            return False
        
        print("✅ OLS Analysis Results:")
        print(f"   R² Score: {metrics['r2']:.3f}")
        print(f"   MAE: {metrics['mae']:,.0f} NOK")
        print(f"   RMSE: {metrics['rmse']:,.0f} NOK")
        print(f"   Intercept (c₀): {metrics['c0']:,.0f} NOK")
        print(f"   Mileage Coeff (c₁): {metrics['c1']:.3f} NOK/km")
        print(f"   Age Coeff (c₂): {metrics['c2']:,.0f} NOK/year")
        print()
        
        # Compare with true coefficients
        print("📊 Coefficient Comparison:")
        print(f"   True c₀: {true_c0:,.0f}, Estimated: {metrics['c0']:,.0f} (error: {abs(true_c0 - metrics['c0'])/true_c0*100:.1f}%)")
        print(f"   True c₁: {true_c1:.3f}, Estimated: {metrics['c1']:.3f} (error: {abs(true_c1 - metrics['c1'])/abs(true_c1)*100:.1f}%)")
        print(f"   True c₂: {true_c2:,.0f}, Estimated: {metrics['c2']:,.0f} (error: {abs(true_c2 - metrics['c2'])/abs(true_c2)*100:.1f}%)")
        print()
        
        # Check usedness score
        if analysis_subset is not None and 'usedness' in analysis_subset.columns:
            print("✅ Usedness score calculated successfully")
            print(f"   Usedness range: {analysis_subset['usedness'].min():.3f} - {analysis_subset['usedness'].max():.3f}")
            
            # Check correlation between usedness and price
            corr = analysis_subset['usedness'].corr(analysis_subset['pris_eks_omreg'])
            print(f"   Usedness-Price correlation: {corr:.3f}")
        else:
            print("❌ Usedness score not calculated")
            return False
        
        print("\n🎉 All tests passed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error during OLS analysis: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_ols_implementation()
    sys.exit(0 if success else 1)
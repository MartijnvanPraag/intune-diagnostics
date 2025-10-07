"""Add agent_framework column to model_configurations table"""

from sqlalchemy import create_engine, text

# Create database engine
engine = create_engine('sqlite:///intune_diagnostics.db')

try:
    with engine.connect() as conn:
        # Add the agent_framework column with default value
        conn.execute(text(
            'ALTER TABLE model_configurations ADD COLUMN agent_framework VARCHAR(50) DEFAULT "autogen"'
        ))
        conn.commit()
        print("✓ Successfully added agent_framework column to model_configurations table")
        print("  Default value: 'autogen'")
        print("  Allowed values: 'autogen' or 'agent_framework'")
except Exception as e:
    print(f"✗ Migration failed: {e}")
    print("  This is expected if the column already exists")

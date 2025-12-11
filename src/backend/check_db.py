import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect(
        'postgresql://citus:Mazikglobal%231@c-webcrawler-db.kouoradmywbe4x.postgres.cosmos.azure.com:5432/webcrawlerdb?sslmode=require'
    )
    
    # Check columns
    r = await conn.fetch("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'crawl_sources' 
        ORDER BY ordinal_position
    """)
    print("Current columns in crawl_sources:")
    for row in r:
        print(f"  - {row['column_name']}")
    
    # Check alembic version
    try:
        v = await conn.fetchrow("SELECT version_num FROM alembic_version")
        print(f"\nAlembic version: {v['version_num'] if v else 'None'}")
    except Exception as e:
        print(f"\nAlembic version check failed: {e}")
    
    await conn.close()

asyncio.run(check())


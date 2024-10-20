-- Create a function to execute arbitrary SQL
CREATE OR REPLACE FUNCTION public.execute_sql(query text)
RETURNS void AS $$
BEGIN
  EXECUTE query;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execute permission to the web_access role (adjust if necessary)
GRANT EXECUTE ON FUNCTION public.execute_sql(text) TO web_access;

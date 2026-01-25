import unittest
import os
import tempfile
from unittest.mock import patch

from ai_masa.comms.load_env import load_env_file

class TestLoadEnv(unittest.TestCase):

    def setUp(self):
        """
        Create a temporary .env file for testing and store original env vars.
        """
        self.original_environ = os.environ.copy()
        
        # Create a temporary file that will be automatically deleted on close
        self.temp_env_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8')
        
        self.env_content = [
            "# This is a comment",
            "BASIC_KEY=basic_value",
            "SPACED_KEY=\"value with spaces\"",
            "QUOTED_KEY='single quoted value'",
            "",
            "  WHITESPACE_KEY  =  value_with_whitespace  ",
            "OVERWRITE_KEY=new_value"
        ]
        
        self.temp_env_file.write('\n'.join(self.env_content))
        self.temp_env_file.close()
        
        # Pre-set an environment variable to test overwriting
        os.environ["OVERWRITE_KEY"] = "old_value"

    def tearDown(self):
        """
        Clean up the temporary file and restore original environment variables.
        """
        os.remove(self.temp_env_file.name)
        os.environ.clear()
        os.environ.update(self.original_environ)

    def test_load_env_file_success(self):
        """
        Tests if variables from the .env file are loaded correctly.
        """
        load_env_file(self.temp_env_file.name)

        # Test basic key-value
        self.assertEqual(os.environ.get("BASIC_KEY"), "basic_value")

        # Test value with spaces and double quotes
        self.assertEqual(os.environ.get("SPACED_KEY"), "value with spaces")
        
        # Test value with single quotes
        self.assertEqual(os.environ.get("QUOTED_KEY"), "single quoted value")
        
        # Test key/value with extra whitespace
        self.assertEqual(os.environ.get("WHITESPACE_KEY"), "value_with_whitespace")

        # Test that comments are not loaded
        self.assertIsNone(os.environ.get("# This is a comment"))

    def test_overwrite_existing_variable(self):
        """
        Tests if an existing environment variable is correctly overwritten.
        """
        # The variable is pre-set to "old_value" in setUp
        self.assertEqual(os.environ.get("OVERWRITE_KEY"), "old_value")
        
        load_env_file(self.temp_env_file.name)
        
        # Verify it has been updated to the value from the file
        self.assertEqual(os.environ.get("OVERWRITE_KEY"), "new_value")

    @patch('builtins.print')
    def test_file_not_found_warning(self, mock_print):
        """
        Tests that a warning is printed when the .env file does not exist.
        """
        non_existent_file = "non_existent.env"
        # Ensure the file doesn't exist
        if os.path.exists(non_existent_file):
            os.remove(non_existent_file)
            
        load_env_file(non_existent_file)

        # Check that a warning message was printed to the console
        mock_print.assert_any_call(f"Warning: .env file not found at {non_existent_file}")

    def test_dynamic_path_resolution(self):
        """
        Tests if `${PWD}` is correctly replaced with the current working directory.
        """
        # Add a line with ${PWD} to our temp file
        with open(self.temp_env_file.name, "a") as f:
            f.write("\nDYNAMIC_PATH=${PWD}/data/logs")

        load_env_file(self.temp_env_file.name)
        
        expected_path = os.path.join(os.getcwd(), 'data', 'logs')
        self.assertEqual(os.environ.get("DYNAMIC_PATH"), expected_path)

if __name__ == "__main__":
    unittest.main()

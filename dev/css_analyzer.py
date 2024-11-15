import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple
from datetime import datetime

"""
CSS Analysis Tool

A comprehensive tool for analyzing CSS files to identify potential issues and patterns.
The analyzer detects:
- Duplicate selectors across the file
- Duplicate properties within selectors
- Commonly used properties across multiple selectors
- Line numbers for all occurrences of selectors

Features:
- Generates timestamped analysis reports
- Handles multi-line CSS rules
- Ignores comments in CSS
- Provides detailed location information
- Error handling for file operations and parsing
"""

def write_to_file(content: str, input_file: str) -> None:
    """
    Write analysis results to a timestamped file in the output folder.
    
    Args:
        content (str): The analysis results to write
        input_file (str): Name of the CSS file being analyzed (used in output filename)
        
    Creates:
        - A 'css_analysis_reports' directory if it doesn't exist
        - A timestamped file containing the analysis results
        
    Output filename format:
        css_analysis_[input_filename]_[YYYYMMDD_HHMMSS].txt
    """
    output_dir = Path('css_analysis_reports')
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_name = Path(input_file).stem
    output_file = output_dir / f"css_analysis_{input_name}_{timestamp}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Analysis written to: {output_file}")

class CSSAnalyzer:
    """
    CSS Analyzer class that performs comprehensive analysis of CSS files.
    
    Attributes:
        css_file_path (Path): Path to the CSS file to analyze
        rules (Dict[str, List[str]]): Dictionary mapping selectors to their properties
        selectors (Dict[str, Set[str]]): Dictionary mapping properties to the selectors that use them
        selector_locations (Dict[str, List[int]]): Dictionary mapping selectors to their line numbers
    """
    
    def __init__(self, css_file_path: str):
        """
        Initialize the CSS analyzer.
        
        Args:
            css_file_path (str): Path to the CSS file to analyze
        """
        self.css_file_path = Path(css_file_path)
        self.rules: Dict[str, List[str]] = defaultdict(list)
        self.selectors: Dict[str, Set[str]] = defaultdict(set)
        self.selector_locations: Dict[str, List[int]] = defaultdict(list)
        
    def parse_css(self) -> None:
        """
        Parse the CSS file and extract rules and properties.
        
        This method:
        1. Reads and decodes the CSS file
        2. Removes comments
        3. Tracks line numbers for each rule
        4. Handles both single-line and multi-line CSS rules
        5. Extracts selectors and their properties
        6. Maintains mappings of selectors to properties and vice versa
        
        Raises:
            FileNotFoundError: If the CSS file doesn't exist
            UnicodeDecodeError: If the file can't be decoded as UTF-8
            Exception: For other parsing errors
        """
        try:
            css_content = self.css_file_path.read_text(encoding='utf-8')
        except FileNotFoundError:
            print(f"Error: File {self.css_file_path} not found!")
            return
        except UnicodeDecodeError:
            print(f"Error: Unable to decode {self.css_file_path}. Make sure it's a valid text file.")
            return
        except Exception as e:
            print(f"Error reading file: {str(e)}")
            return
            
        try:
            # Remove comments
            css_content = re.sub(r'/\*[\s\S]*?\*/', '', css_content)
            
            lines = css_content.split('\n')
            current_line = 0
            
            # Parse rules while tracking line numbers
            rule_blocks = []
            in_rule = False
            current_selector = ""
            current_properties = []
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                    
                if not in_rule and '{' in line:
                    # Start of a new rule
                    current_selector = line[:line.find('{')].strip()
                    self.selector_locations[current_selector].append(line_num)
                    properties_start = line[line.find('{')+1:]
                    if '}' in properties_start:
                        # Single-line rule
                        properties = properties_start[:properties_start.find('}')]
                        rule_blocks.append((current_selector, properties, line_num))
                        current_selector = ""
                    else:
                        # Multi-line rule starts
                        in_rule = True
                        current_properties = [properties_start]
                elif in_rule and '}' in line:
                    # End of multi-line rule
                    current_properties.append(line[:line.find('}')])
                    properties = ' '.join(current_properties)
                    rule_blocks.append((current_selector, properties, self.selector_locations[current_selector][-1]))
                    current_selector = ""
                    current_properties = []
                    in_rule = False
                elif in_rule:
                    # Middle of multi-line rule
                    current_properties.append(line)
            
            # Process all collected rules
            for selector, properties, line_num in rule_blocks:
                properties = [p.strip() for p in properties.strip().split(';') if p.strip()]
                
                for prop in properties:
                    if ':' in prop:
                        self.rules[selector].extend([prop])
                        prop_name = prop.split(':')[0].strip()
                        self.selectors[prop_name].add(selector)
        except Exception as e:
            print(f"Error parsing CSS: {str(e)}")
            return
                        
    def find_duplicate_selectors(self) -> Dict[str, List[int]]:
        """
        Find selectors that appear multiple times in the CSS file.
        
        Returns:
            Dict[str, List[int]]: Dictionary mapping selectors to lists of line numbers 
                                 where they appear, only for selectors that appear multiple times
        """
        return {
            selector: locations
            for selector, locations in self.selector_locations.items()
            if len(locations) > 1
        }
        
    def find_duplicates(self) -> Dict[str, List[str]]:
        """
        Find duplicated properties within selectors.
        
        Returns:
            Dict[str, List[str]]: Dictionary mapping selectors to their duplicate properties,
                                 where each property maps to its different values
        """
        duplicates = {}
        
        for selector, properties in self.rules.items():
            prop_count = defaultdict(list)
            
            for prop in properties:
                if ':' in prop:
                    prop_name, prop_value = [p.strip() for p in prop.split(':', 1)]
                    prop_count[prop_name].append(prop_value)
            
            selector_duplicates = {
                prop: values for prop, values in prop_count.items()
                if len(values) > 1
            }
            
            if selector_duplicates:
                duplicates[selector] = selector_duplicates
                
        return duplicates
    
    def find_common_properties(self, threshold: int = 3) -> Dict[str, Set[str]]:
        """
        Find properties that are used in multiple selectors above a threshold.
        
        Args:
            threshold (int): Minimum number of occurrences to consider a property common.
                           Defaults to 3.
        
        Returns:
            Dict[str, Set[str]]: Dictionary mapping property names to sets of selectors 
                                that use them, only for properties used >= threshold times
        """
        return {
            prop: selectors
            for prop, selectors in self.selectors.items()
            if len(selectors) >= threshold
        }
    
    def analyze(self) -> None:
        """
        Perform complete CSS analysis and write results to file.
        
        This method:
        1. Verifies the input file exists
        2. Parses the CSS file
        3. Analyzes for duplicate selectors
        4. Analyzes for duplicate properties within selectors
        5. Identifies commonly used properties
        6. Writes a comprehensive report to a timestamped file
        
        The analysis report includes:
        - File information
        - Duplicate selector locations
        - Duplicate properties within selectors
        - Properties used in 3 or more selectors
        """
        try:
            output = []
            
            if not self.css_file_path.exists():
                output.append(f"Error: File {self.css_file_path} not found!")
                return
                
            output.append(f"Analyzing CSS file: {self.css_file_path}\n")
            
            self.parse_css()
            
            # Analyze and report duplicate selectors
            duplicate_selectors = self.find_duplicate_selectors()
            if duplicate_selectors:
                output.append("=== Duplicate Selectors Found ===")
                for selector, lines in duplicate_selectors.items():
                    output.append(f"\nSelector '{selector}' appears {len(lines)} times:")
                    output.append(f"  Line numbers: {', '.join(str(line) for line in lines)}")
            else:
                output.append("No duplicate selectors found.")
            
            # Analyze and report duplicate properties
            duplicates = self.find_duplicates()
            if duplicates:
                output.append("\n=== Duplicate Properties Found ===")
                for selector, props in duplicates.items():
                    output.append(f"\nSelector: {selector}")
                    for prop, values in props.items():
                        output.append(f"  Property '{prop}' is defined multiple times with values:")
                        for value in values:
                            output.append(f"    - {value}")
            else:
                output.append("\nNo duplicate properties found within selectors.")
                
            # Analyze and report common properties
            output.append("\n=== Commonly Used Properties ===")
            common_props = self.find_common_properties()
            if common_props:
                for prop, selectors in common_props.items():
                    output.append(f"\nProperty '{prop}' is used in {len(selectors)} selectors:")
                    for selector in sorted(selectors):
                        output.append(f"  - {selector}")
            else:
                output.append("No properties used in 3 or more selectors.")
                
            # Write the complete analysis to file
            write_to_file('\n'.join(output), str(self.css_file_path))
            
        except Exception as e:
            print(f"Error during analysis: {str(e)}")

def main():
    """
    Main entry point for the CSS analyzer.
    
    Usage:
        python css_analyzer.py <css_file_path>
    
    The script will analyze the specified CSS file and generate a detailed report
    in the css_analysis_reports directory.
    """
    try:
        import sys
        
        if len(sys.argv) != 2:
            print("Usage: python css_analyzer.py <css_file_path>")
            sys.exit(1)
            
        analyzer = CSSAnalyzer(sys.argv[1])
        analyzer.analyze()
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()
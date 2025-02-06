from typing import Union
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import WebDriverException
import time
import pandas as pd
import os 
import re 
import warnings

from . import logger, scraper

# Create module-specific logger
logger = logger.getChild('utils')

##### Get the directory where this file is housed ########################
wd = os.path.dirname(__file__)
fdel= os.path.sep

def check_browser_installed():
    """Check if browsers are installed using Selenium's service checks"""
    firefox_available = False
    chrome_available = False
    
    try:
        firefox_service = FirefoxService()
        firefox_service.is_connectable()  # This checks if Firefox is available
        firefox_available = True
    except WebDriverException:
        pass

    try:
        chrome_service = ChromeService()
        chrome_service.is_connectable()  # This checks if Chrome is available
        chrome_available = True
    except WebDriverException:
        pass

    if not (firefox_available or chrome_available):
        warnings.warn(
            "Neither Firefox nor Chrome browser found. Please install one of them to use this package."
            "Firefox: https://www.mozilla.org/en-US/firefox/new/"
            "Google Chrome: https://www.google.com/chrome/ ",
            RuntimeWarning
        )
    
    return firefox_available, chrome_available

## Standalone functions  ########################################
def export_html(html: str, save_path: str = wd+fdel+'last_soup.html'):
    with open(save_path, 'w') as wp:
        wp.write(html)
    return None

def split_numeric(input_string: str):
    # Match integers or decimal numbers
    # Match numbers including metric suffixes
    if not isinstance(input_string, str):
        #print("split_numeric function: Input is not a string, returning input.")
        return input_string
    else:
        number_pattern = r'-?\d*\.?\d+[KMGBT]?'
        
        # Find the numeric part
        match = re.search(number_pattern, input_string)
        
        if match:
            numeric_part = match.group()
            # Replace the numeric part with empty string to get remainder
            non_numeric = re.sub(number_pattern, '', input_string)
            return numeric_part, non_numeric.strip()
        else:   
            return input_string

def map_frequency(diff):
    """Map timedelta to frequency string"""
    days = diff.days
    if days > 0 and days <= 3:
        return "D"
    elif days > 3 and days <= 14:
        return "W"
    elif days > 14 and days <= 60:
        return "MS"
    elif days > 60 and days <= 120:
        return "QS"
    elif days > 120 and days <= 420:
        return "AS"
    else:
        return "Multi-year"
    
def get_date_frequency(date_series: pd.Series):
    """Get the frequency of a date series"""
    if date_series.is_monotonic_increasing or date_series.is_monotonic_decreasing:
        diff = date_series.diff().dropna().mean()
        freq = pd.infer_freq(date_series)
        if freq is not None:
            return freq
        else:
            return map_frequency(diff)
    else:
        return None
    
# BeautifulSoup approach
def check_element_exists_bs4(soup, selector):
    try:
        element = soup.select_one(selector)
        return element.text if element else None
    except:
        return None

def convert_metric_prefix(value_str: str) -> float:
    """Convert string with metric prefix to float
    e.g., '1.3K' -> 1300, '2.6M' -> 2600000
    """
    # Dictionary of metric prefixes and their multipliers
    metric_prefixes = {
        'K': 1000,
        'M': 1000000, 
        'B': 1000000000,
        'G': 1000000000,
        'T': 1000000000000}
    
    # Clean and standardize input
    value_str = value_str.strip().upper()
    
    try:
        # Match number and prefix
        match = re.match(r'^(-?\d*\.?\d+)([KMGBT])?$', value_str)
        if match:
            number, prefix = match.groups()
            number = float(number)
            # Multiply by prefix value if present
            if prefix and prefix in metric_prefixes:
                number *= metric_prefixes[prefix]
            return number
        return float(value_str)  # No prefix case
    except:
        print(f"Error converting value: {value_str}")
        return value_str  # Return original if conversion fails
    
def ready_datestr(date_str: str):
    """Replace substrings in datestr using a dictionary to get the string ready
    for parsing to datetime. Using QS frequency convention for quarters."""
    
    quarters = {"Q1": "January",
                "Q2": "April",
                "Q3": "July",
                "Q4": "October"}

    for key, value in quarters.items():
        date_str = date_str.replace(key, value)
    return date_str
    
def normalize_series(series, new_min, new_max):
    """
    Normalize a pandas Series to a given range [new_min, new_max].

    Parameters:
    series (pd.Series): The pandas Series to normalize.
    new_min (float): The minimum value of the new range.
    new_max (float): The maximum value of the new range.

    Returns:
    pd.Series: The normalized pandas Series.
    """
    series_min = series.min()
    series_max = series.max()
    normalized_series = (series - series_min) / (series_max - series_min) * (new_max - new_min) + new_min
    return normalized_series

def invert_series(series: pd.Series, max_val: float = None):
    """
    Invert a pandas Series.

    Parameters:
    series (pd.Series): The pandas Series to invert.

    Returns:
    pd.Series: The inverted pandas Series.
    """
    if max_val is None:
        max_val = series.max()
        print(f"Max value: {max_val}, subtracting series from this value.")
    return (max_val - series) #+ series.min()

def find_zero_crossing(series):
    """Find the x-intercept (value where series crosses zero) using linear interpolation"""
    if not ((series.min() < 0) and (series.max() > 0)):
        return None
        
    # Find where values change sign
    for i in range(len(series)-1):
        if (series.iloc[i] <= 0 and series.iloc[i+1] > 0) or \
           (series.iloc[i] >= 0 and series.iloc[i+1] < 0):
            # Get x values (index values)
            x1, x2 = series.index[i], series.index[i+1]
            # Get y values
            y1, y2 = series.iloc[i], series.iloc[i+1]
            # Linear interpolation to find x-intercept
            zero_x = x1 + (0 - y1)*(x2 - x1)/(y2 - y1)
            return zero_x
            
    return None

def round_to_month_start(dates: pd.DatetimeIndex):
    """Round dates to nearest month start.
    
    Args:
        dates: DatetimeIndex of dates to round
        
    Returns:
        DatetimeIndex: Dates rounded to nearest month start
    """
    def _round_single_date(dt):
        if dt.day > 15:
            # Roll forward to next month start
            if dt.month == 12:
                return pd.Timestamp(f"{dt.year + 1}-01-01")
            else:
                return pd.Timestamp(f"{dt.year}-{dt.month + 1:02d}-01")
        else:
            # Roll back to current month start
            return pd.Timestamp(f"{dt.year}-{dt.month:02d}-01")

    rounded_dates = [_round_single_date(dt) for dt in dates]
    return pd.DatetimeIndex(rounded_dates)

########### Classes ##############################################################################


class TooltipScraper(scraper.TE_Scraper):
    """ Extended version of TE_Scraper with additional functionality to scrape tooltip data from a chart element using Selenium.
    Can be initilized using a TE_Scraper object or a new URL. If using a new URL, a new webdriver will be created. If using an existing
    TE_Scraper object, the webdriver from that object will be used and all attributes will be copied over.
    This can get x, y data from the tooltip box displayed by a site such as Trading Economics when the cursor
    is moved over a chart. It can move the cursor to specific points on the chart and extract tooltip text.
    It extracts date and value data from the tooltip text.
    Initialize the scraper with a URL and chart coordinates

    **init Parameters:**
    - parent_instance (scraper.TE_Scraper): A parent scraper object to copy attributes from. This is the most efficient way to initialize.
    - **kwargs: Keyword arguments to pass to the parent class, these are TE_Scraper init key word arguments.
    Generally you would not supply keyword arguments if you are using a parent_instance for initilization. The kwargs apply to creation
    of a new TE_Scraper object. See TE_scraper class for details on initialization of a fresh instance.

    """
    
    def __init__(self, parent_instance=None, **kwargs):
        """ Initialize the TooltipScraper object"""
        if parent_instance:  # Copy attributes from parent instance
            self.__dict__.update(parent_instance.__dict__)
            self.observers.append(self)
        else:
            super().__init__(**kwargs)

    def get_chart_dims(self):
        """Get dimensions of chart and plotting area"""
        try:
            # Ensure full_chart is WebElement
            self.chart_element = self.driver.find_element(By.CSS_SELECTOR, "#chart")
                
            # Get overall chart dimensions
            self.chart_rect = {k: round(float(v), 1) for k, v in self.chart_element.rect.items()}
            
            # Get plot area dimensions
            self.plot_background = self.driver.find_element(By.CSS_SELECTOR, '.highcharts-plot-background')
            self.axes_rect = {k: round(float(v), 1) for k, v in self.plot_background.rect.items()}
            self.chart_x = self.axes_rect["width"]
            self.chart_y = self.axes_rect["height"]
            return True
        
        except Exception as e:
            print(f"Failed to get chart dimensions: {e}")
            logger.error(f"Failed to get chart dimensions: {e}")
            return False
    
    def move_cursor(self, x: int = 0, y: int = 0):
        self.actions.move_to_element_with_offset(self.full_chart, x, y).perform()
        print(f"Moved cursor to ({x}, {y})")
        return None
                        
    def move_pointer(self, x_offset: int = None, y_offset: int = 1, x_increment: int = 1):
        """Move cursor to a specific x-offset and y-offset from the chart element.
        Uses Selenium ActionChains to move the cursor."""

        if x_offset is None:
            x = 0
            while x < self.chart_x:
                self.move_cursor(x, y_offset)
                time.sleep(1)
                if self.get_tooltip_text():
                    break
                x += x_increment
            return True
        else:
            self.move_cursor(x, y_offset)
            time.sleep(1)
            if self.get_tooltip_text():
                return True
            else:
                return False
    
    def first_last_dates(self):
        """Scrape first and last data points for the data series on the chart at TE using viewport coordinates.

        **Returns:**
        - start_end: dict containing the start and end dates and values of the data series.

        """

        # try:
        self.update_chart()
        # determine_chart_method is inactive as of now...
        #self.determine_chart_type()
        self.select_line_chart() ## MAKE SURE IT IS A LINECHART.
        self.determine_date_span()

        if not hasattr(self, "axes_rect"):
            print("Getting chart dimensions and plot background element.")
            if self.get_chart_dims():
                print("Got chart dimensions and plot background element.")

        # Calculate exact positions of left and right extremes
        left_x =  self.axes_rect['x'] # Left edge x-coordinate
        right_x = self.axes_rect['x'] + self.axes_rect['width'] # Right edge x-coordinate
        y_pos = self.axes_rect["y"] + round(self.axes_rect["height"]/2)  # Middle of chart
        # NOTE: USING THE MIDDLE OF THE CHART (in Y) WILL REQUIRE LINE CHART_TYPE.
        
        # Initialize ActionChains
        actions = ActionChains(self.driver)
        start_end = {}
        
        # For each extreme (left and right)
        positions = {
            ("start_date", "start_value"): left_x,
            ("end_date", "end_value"): right_x
        }

        for (date_key, value_key), x_pos in positions.items():
            # Reset cursor by moving to plot background first
            actions.move_to_element(self.plot_background).perform()
            actions.reset_actions()
            
            # Move to exact position
            actions.move_by_offset(x_pos, y_pos).perform()
            print(f"Moved cursor to ({x_pos}, {y_pos})")
            time.sleep(0.5)
            
            # Get tooltip
            tooltip = self.get_tooltip_text()
            if tooltip:
                date, value = self.extract_date_value_tooltip(tooltip)
                if date and value:
                    start_end[date_key] = date
                    start_end[value_key] = value
        
        return start_end
            
        # except Exception as e:
        #     logger.error(f"Error in first_last_dates: {e}")
        #     return None
    
    def get_latest_points(self, num_points: int = 10, x_increment: int = 1): #To do: The tooltip scraper class should perhaps inherit from this TE_SCraper so attrubutes such as datespan can be accessed.
        """ Scrape the latest points to determine the time-series frequency. Will also check if end_date is correct.
        This will work best if the chart is set to 1Y datespan first before the tooltip scraper object is initialized.

        **Parameters:**

        - num_points (int): The number of data points to scrape from the 1Y chart.
        - x_increment (int): The number of pixels to move cursor horizontally between points.

        **Returns:**

        - data_points (list): A list of dictionaries containing scraped data points.
        - num_points (int): The number of data points scraped."""

        if self.date_span != "1Y":
            self.set_date_span("1Y")
        
        self.select_line_chart() #Force line chart selection - very important.
        
        self.update_chart()
        if not hasattr(self, "axes_rect"):
            self.get_chart_dims()

        if not hasattr(self, "viewport_width"):
            self.viewport_width = self.driver.execute_script("return window.innerWidth;")
            self.viewport_height = self.driver.execute_script("return window.innerHeight;")
        
        print(f"Viewport dimensions: {self.viewport_width} x {self.viewport_height}")
        print(f"Chart position in viewport: x={self.axes_rect['x']}, y={self.axes_rect['y']}")
        
        data_points = []
        last_tooltip = ""
        viewport_y = self.axes_rect['y'] + round(self.axes_rect['height'] / 2)

        actions = ActionChains(self.driver); actions.reset_actions()
        # Move cursor to chart middle to start at right edge.
        actions.move_to_element_with_offset(self.plot_background, round(self.chart_x/2), 0).perform()
        chart_edge = self.axes_rect["x"] + round(self.chart_x/2); print(chart_edge)
        i = 1
        while len(data_points) < num_points:
            #try: 
            actions.move_by_offset(-i, 0).perform()
            time.sleep(0.05)
            
            tooltip = self.get_tooltip_text()
            date, value = self.extract_date_value_tooltip(tooltip)
            
            if tooltip == last_tooltip:
                #print(f"Date not changed from last point, skipping: {date}")
                i += 1
                continue

            if tooltip and date and value:
                #print("Data point scraped: ", date, value)  
                data_points.append({
                    'viewport_x': self.axes_rect["x"] + i,
                    'viewport_y': viewport_y,
                    'tooltip_data': tooltip,
                    "date": date,
                    "value": value
                })
                i += 1
            else:
                print(f"No tooltip found at point")
            
            last_tooltip = tooltip
        
        return data_points
    
    def get_device_pixel_ratio(self):
        """Get device pixel ratio to scale movements"""
        return self.driver.execute_script('return window.devicePixelRatio;')
        
    def extract_date_value_tooltip(self, tooltip_element: str):
        """Extract date and value from a single tooltip HTML"""

        # try:
        # Parse tooltip HTML
        soup = BeautifulSoup(tooltip_element, 'html.parser')
        
        # Extract date and value
        date = soup.select_one('.tooltip-date').text.strip()
        date = ready_datestr(date)
        
        value = soup.select_one('.tooltip-value').text.replace(' Points', '')
        #print("Date: ", date, "Value: ", value)
        try:
            value = float(value)
        except:
            pass
        
        try:
            date = pd.to_datetime(date)
        except:
            print(f"Error converting date string: {date}")
            pass
        
        # try:
        splitted = split_numeric(value)
        if isinstance(splitted, tuple):
            value = convert_metric_prefix(splitted[0])
        else:
            value = splitted

            # except Exception as e:
            #     print(f"Error converting value string: {value}")
            #     return
            
        # except Exception as e:
        #     print(f"Error parsing tooltip data: {str(e)}")
        #     return None
    
        return date, value
        
    def scrape_chart_data(self):
        """Scrape data points by moving cursor across chart within viewport bounds
        I don't know if this is working atm, this approcach of pulling each datapoint one at a time from the tooltips
        may be implemented later yet it will need javascript implementation to work fast enough.
        Currently this is very slow when done this way. """

        self.update_chart()
        
        # Get chart dimensions and position
        chart_rect = self.full_chart.rect
        chart_width = chart_rect['width']
        chart_height = chart_rect['height']
        
        # Find chart center in viewport coordinates
        chart_center_x = chart_rect['x'] + (chart_width / 2)
        chart_center_y = chart_rect['y'] + (chart_height / 2)
        print(f"Chart center: ({chart_center_x}, {chart_center_y})")
        
        # Calculate valid x-coordinate range
        x_start = chart_center_x - (chart_width / 2)  # Leftmost valid x
        x_end = chart_center_x + (chart_width / 2)    # Rightmost valid x
        
        # Initialize data collection
        data_points = []
        x_increment = 2
        
        # Move cursor left to right within valid range
        current_x = x_start

        while current_x <= x_end:
            try:
                # Calculate offset from chart center
                x_offset = current_x - chart_center_x
                
                # Move cursor using offset from center
                self.actions.move_to_element(self.full_chart)\
                        .move_by_offset(x_offset, 0)\
                        .perform()
                
                time.sleep(0.2)
                
                # Get tooltip data
                tooltip = self.get_tooltip_text()
                if tooltip:
                    data_points.append({
                        'x_position': current_x,
                        'tooltip_data': tooltip
                    })
                
                current_x += x_increment
                
            except Exception as e:
                print(f"Error at x={current_x}: {str(e)}")
                current_x += x_increment
                
        return data_points

    def get_tooltip_text(self, tooltip_selector: str = '.highcharts-tooltip'):
        """Get tooltip text from the chart element"""

        # Locate the tooltip element and extract the text
        tooltip_elements = self.driver.find_elements(By.CSS_SELECTOR, tooltip_selector)
        if tooltip_elements:
            for tooltip_element in tooltip_elements:
                tooltip_text = tooltip_element.get_attribute("outerHTML")
                #print(tooltip_text)
            return tooltip_text
        else:
            #print("Tooltip not found")
            return None
        
        
    def show_position_marker(self, x: int, y: int, duration_ms: int = 5000):
        """Add visual marker at specified coordinates"""
        js_code = """
            // Create dot element
            const dot = document.createElement('div');
            dot.style.cssText = `
                position: absolute;
                left: ${arguments[0]}px;
                top: ${arguments[1]}px;
                width: 10px;
                height: 10px;
                background-color: red;
                border-radius: 50%;
                z-index: 9999;
                pointer-events: none;
            `;
            document.body.appendChild(dot);
            
            // Remove after duration
            setTimeout(() => dot.remove(), arguments[2]);
        """
        self.driver.execute_script(js_code, x, y, duration_ms)

    def mark_cursor_position(self, duration_ms: int = 5000):
        """Mark current cursor position with dot"""
        js_code = """
            let cursor_x = 0;
            let cursor_y = 0;
            
            document.addEventListener('mousemove', function(e) {
                cursor_x = e.pageX;
                cursor_y = e.pageY;
            });
            
            return [cursor_x, cursor_y];
        """
        coords = self.driver.execute_script(js_code)
        if coords and len(coords) == 2:
            self.show_position_marker(coords[0], coords[1], duration_ms)
            return coords
        return None

    def move_cursor_on_chart(self, x: int = 0, y: int = 0):
        """Move cursor to chart origin (0,0) point"""
        
        print(f"Chart rect: {self.axes_rect}")
        # Calculate origin coordinates in viewport
        x_pos = self.full_chart.rect["x"] + float(self.axes_rect['x'])  + x
        y_pos = self.full_chart.rect["y"] + float(self.axes_rect['y']) + float(self.axes_rect["height"]) - y  
        
        # Move to origin
        actions = ActionChains(self.driver)
        actions.move_by_offset(x_pos, y_pos).perform()
        actions.reset_actions()
        self.show_position_marker(x_pos, y_pos)
        print(f"Moved cursor to chart pposition ({x_pos}, {y_pos})")
    
    def bail_out(self):
        self.driver.quit()
        return None
    
    def move_with_marker(self, x: int, y: int):
        """Move to position and show marker"""
        actions = ActionChains(self.driver)
        actions.move_by_offset(x, y).perform()
        actions.reset_actions()
        self.show_position_marker(x, y)
    

### Other utility functions for the TooltipScraper class ##########################################

def get_chart_datespans(scraper_object: Union[scraper.TE_Scraper, TooltipScraper], selector: str = "#dateSpansDiv"):
    """Get the date spans from the Trading Economics chart currently displayed in the scraper object. The scraper object can be a TE_Scraperfrom the scraper module
    or TooltipScraper object from the utils module.
    
    ** Parameters:**
    - scraper_object (TE_Scraper or TooltipScraper): The scraper object with the chart to scrape.
    - selector (str): The CSS selector to find the date spans element. Default is '#dateSpansDiv'.
    
    ** Returns:**
    - date_spans (dict): A dictionary with date span names as keys and CSS selectors for the button to select that span as values.
    """
    if not isinstance(scraper_object, TooltipScraper) or not isinstance(scraper_object, scraper.TE_Scraper):
        print("get_chart_datespans function: Invalid scraper object supplies as first arg, must be a scraper.TE_Scraper or utils.TooltipScraper object.")
        return None
    try:
        buts = scraper_object.page_soup.select_one(selector)
        datebut = buts[0] if isinstance(buts, list) else buts
        scraper_object.date_spans = {child.text: f"a.{child['class'][0] if isinstance(child['class'], list) else child['class']}:nth-child({i+1})" for i, child in enumerate(datebut.children)}
        return scraper_object.date_spans
    except Exception as e:
        print(f"get_chart_datespans function: Error finding date spans, error: {str(e)}")
        return None

def click_button(scraper_object: Union[scraper.TE_Scraper, TooltipScraper], 
                 selector: str = "#dateSpansDiv", 
                 selector_type=By.CSS_SELECTOR):
    
    """Click button and wait for response..."""

    try:
        # Wait for element to be clickable
        button =  WebDriverWait(scraper_object.driver, timeout=10).until(
            EC.element_to_be_clickable((selector_type, selector))
        )
        # Scroll element into view
        #self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
        time.sleep(0.25)  # Brief pause after scroll
        button.click()
        #logger.info("Button clicked successfully, waiting 1s for response...")
        logger.info(f"Button clicked successfully: {selector} on object {scraper_object}")
        time.sleep(0.75)
        return True

    except Exception as e:
        logger.info(f"Error clicking button: {str(e)} on object {scraper_object}")
        return False
    
def show_position_marker(scraper_object: Union[scraper.TE_Scraper, TooltipScraper], 
                         x: int, y: int, duration_ms: int = 5000):
    """Add visual marker at specified coordinates"""

    if not isinstance(scraper_object, TooltipScraper) or not isinstance(scraper_object, scraper.TE_Scraper):
        print("get_chart_datespans function: Invalid scraper object supplies as first arg, must be a scraper.TE_Scraper or utils.TooltipScraper object.")
        return None
    
    js_code = """
        // Create dot element
        const dot = document.createElement('div');
        dot.style.cssText = `
            position: absolute;
            left: ${arguments[0]}px;
            top: ${arguments[1]}px;
            width: 10px;
            height: 10px;
            background-color: red;
            border-radius: 50%;
            z-index: 9999;
            pointer-events: none;
        `;
        document.body.appendChild(dot);
        
        // Remove after duration
        setTimeout(() => dot.remove(), arguments[2]);
    """
    scraper_object.driver.execute_script(js_code, x, y, duration_ms)
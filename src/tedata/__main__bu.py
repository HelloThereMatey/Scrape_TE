from typing import Literal
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import time
import pandas as pd
import time
import os 
import re 

##### Get the directory where this file is housed ########################
wd = os.path.dirname(__file__)
fdel= os.path.sep

## Standalone functions  ########################################
def export_html(html: str, save_path: str = wd+fdel+'last_soup.html'):
    with open(save_path, 'w') as wp:
        wp.write(html)
    return None

def find_element_header_match(soup: BeautifulSoup, selector: str, match_text: str):
    """Find .card-header element with text matching search_text"""
    elements = soup.select(selector)
    print("Elements found from selector, number of them: ", len(elements))
    for ele in elements:
        print("\n", str(ele), "\n")
        if str(ele.header.text).strip().lower() == match_text.lower():
            print("Match found: ", ele.header.text)
            return ele
    return None

def split_numeric(input_string: str):
    # Match integers or decimal numbers
    # Match numbers including metric suffixes
    if not isinstance(input_string, str):
        print("split_numeric function: Input is not a string, returning input.")
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

########### Classes ##############################################################################

class get_tooltip(object):
    """Class to scrape tooltip data from a chart element using Selenium.
    This can get x, y data from the tooltip box displayed by a site such as Trading Economics when the cursor
    is moved over a chart. It can move the cursor to specific points on the chart and extract tooltip text.
    It extracts date and value data from the tooltip text.
    """

    def __init__(self, 
                    driver: webdriver = None, 
                    url: str = None,
                    chart_x: int = 600, chart_y: int = 375):
        
        """Initialize the scraper with a URL and chart coordinates
        **Parameters:**
        - driver (webdriver): A Selenium WebDriver object, can put in an active one or make a new one for a new URL.
        - url (str): The URL of the webpage to scrape. Unnecessary if driver is provided.
        - chart_x (float): The total length in pixels of the svg chart image that we are trying to scrape.
        - chart_y (float): The total height in pixels of the svg chart image that we are trying to scrape.
        """
        if driver is None:
            self.driver = webdriver.Firefox()
            self.driver.get(url)
        else:
            self.driver = driver
        self.chart_x = round(chart_x)
        self.chart_y = round(chart_y)

        self.last_url = url

        #wait for the chart element to be present
        chart_selector = '.highcharts-plot-background'
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, chart_selector))
        )

        # Locate the chart element
        self.chart_element = self.driver.find_element(By.CSS_SELECTOR, chart_selector)

        # Initialize ActionChains
        self.actions = ActionChains(self.driver)

    def move_cursor(self, x: int = 0, y: int = 0):
        self.actions.move_to_element_with_offset(self.chart_element, x, y).perform()
        print(f"Moved cursor to ({x}, {y})")
        return
                        
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
    
    def scrape_dates_from_tooltips(self, num_points: int = 10, x_increment: int = 1):
        """Scrape first and last data points using viewport coordinates.
        Also scrape dates from the first n points to determine time series frequency.
        **Parameters:**
        - num_points (int): The number of data points to scrape in addition to first and last points.
        - x_increment (int): The number of pixels to move cursor horizontally between points.
        **Returns:**
        - data_points (list): A list of dictionaries containing scraped data points.
        - num_points (int): The number of data points scraped."""
        
        # Get chart element and viewport info
        chart_rect = self.chart_element.rect
        viewport_width = self.driver.execute_script("return window.innerWidth;")
        viewport_height = self.driver.execute_script("return window.innerHeight;")
        
        print(f"Viewport dimensions: {viewport_width} x {viewport_height}")
        print(f"Chart position in viewport: x={chart_rect['x']}, y={chart_rect['y']}")
        
        data_points = []
        i = 0
        last_date = ""
        viewport_y = chart_rect['y'] + (chart_rect['height'] / 2)
        last_x =  chart_rect['x'] + chart_rect['width']
        date_change = []
        just_run = False
        date_change_count = 0

        while len(data_points) < num_points + 2:  #scrape first 10 points and then last point...
            try: 
                # Use ActionChains to move to absolute viewport position
                actions = ActionChains(self.driver)
                if len(data_points) == num_points + 1:
                    print("Scraping the last point now at x = ", last_x)
                    x_pos = last_x
                else:
                    x_pos = chart_rect['x'] + i*x_increment

                actions.move_by_offset(x_pos, viewport_y).perform()
                actions.reset_actions()  # Reset for next move
                #print(f"Moving to point at viewport coordinates ({x_pos}, {viewport_y})")
                time.sleep(0.05)
                
                tooltip = self.get_tooltip_text()
                date, value = self.extract_date_value_tooltip(tooltip)

                if not just_run:
                    if date == last_date:
                        i += 1
                        date_change_count += 1
                        continue
                    else:   
                        date_change.append(date_change_count)
                        date_change_count = 0
                        # Here we're trying to find the average number f pixels needed to move betweeen dates from the 1st 3 points to speed up subsequent scraping.
                        if len(date_change) == 3:
                            #print("Here's the date change list: ", date_change[1::])
                            av_incs = sum(date_change[1::])/2
                            x_increment = round(av_incs)
                            just_run == True
                
                if date == last_date:
                    #print(f"Date not changed from last point, skipping: {date}")
                    i += 1
                    continue

                if tooltip and date and value:
                    #print(f"Found point data: {date}, {value}")

                    data_points.append({
                        'viewport_x': x_pos,
                        'viewport_y': viewport_y,
                        'tooltip_data': tooltip,
                        "date": date,
                        "value": value
                    })
                else:
                    print(f"No tooltip found at point")
                
                last_date = date
            except Exception as e:
                print(f"Error scraping tooltip at ({x_pos}, {viewport_y}), error: {str(e)}")
                continue
        
        return data_points, num_points
    
    def extract_date_value_tooltip(self, tooltip_element: str):
        """Extract date and value from a single tooltip HTML"""

        # try:
        # Parse tooltip HTML
        soup = BeautifulSoup(tooltip_element, 'html.parser')
        
        # Extract date and value
        date = soup.select_one('.tooltip-date').text.strip()
        date = ready_datestr(date)
        
        value = soup.select_one('.tooltip-value').text.replace(' Points', '')
        print("Date: ", date, "Value: ", value)
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
        
        # Get chart dimensions and position
        chart_rect = self.chart_element.rect
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
                self.actions.move_to_element(self.chart_element)\
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
            print("Tooltip not found")
            return None
    
    def bail_out(self):
        self.driver.quit()
        return None
    
################# Selenium classes below ##########################################

class generic_webdriver(object):
    """Generic webdriver class for initializing a Selenium WebDriver"""

    # Define browser type with allowed values
    BrowserType = Literal["chrome", "firefox"]
    def __init__(self, driver: webdriver = None, 
                 browser: BrowserType = "firefox", 
                 headless: bool = True):
        
        self.browser = browser
        self.headless = headless

        if driver is None:
            if browser == "chrome":
                options = webdriver.ChromeOptions()
                if headless:
                    options.add_argument('--headless')
                self.driver = webdriver.Chrome(options=options)
            elif browser == "firefox":
                options = webdriver.FirefoxOptions()
                if headless:
                    options.add_argument('--headless')
                self.driver = webdriver.Firefox(options=options)
            else:
                raise ValueError("Unsupported browser! Use 'chrome' or 'firefox'.")
        else:
            self.driver = driver
        
        self.wait = WebDriverWait(self.driver, timeout=10)


### Main workhorse class for scraping data from Trading Economics website.
class TE_Scraper(object):
    """Class for scraping data from Trading Economics website. This is the main workhorse of the module.
    It is designed to scrape data from the Trading Economics website using Selenium and BeautifulSoup.
    It can load a page, click buttons, extract data from elements, and plot the extracted data.

    **Init Parameters:** 

    - driver (webdriver): A Selenium WebDriver object, can put in an active one or make a new one for a new URL.
    - browser (str): The browser to use for scraping, either 'chrome' or 'firefox'.
    - headless (bool): Whether to run the browser in headless mode (show no window).
    """

    # Define browser type with allowed values
    BrowserType = Literal["chrome", "firefox"]
    def __init__(self, driver: webdriver = None, 
                 browser: BrowserType = "firefox", 
                 headless: bool = True):
        
        self.browser = browser
        self.headless = headless

        if driver is None:
            if browser == "chrome":
                options = webdriver.ChromeOptions()
                if headless:
                    options.add_argument('--headless')
                self.driver = webdriver.Chrome(options=options)
            elif browser == "firefox":
                options = webdriver.FirefoxOptions()
                if headless:
                    options.add_argument('--headless')
                self.driver = webdriver.Firefox(options=options)
            else:
                raise ValueError("Unsupported browser! Use 'chrome' or 'firefox'.")
        else:
            self.driver = driver
        
        self.wait = WebDriverWait(self.driver, timeout=10)
        self.start_end = None
    
    def load_page(self, url, wait_time=5):
        """Load page and wait for it to be ready"""

        self.last_url = url
        self.series_name = url.split("/")[-1].replace("-", " ")
        try:
            self.driver.get(url)
            time.sleep(wait_time)  # Basic wait for page load
            self.full_page = self.get_page_source()
            self.page_soup = BeautifulSoup(self.full_page, 'html.parser')
            return True
        except Exception as e:
            print(f"Error loading page: {str(e)}")
            return False
    
    def click_button(self, selector, selector_type=By.CSS_SELECTOR):
        """Click button and wait for response"""

        try:
            # Wait for element to be clickable
            button = self.wait.until(
                EC.element_to_be_clickable((selector_type, selector))
            )
            # Scroll element into view
            #self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
            time.sleep(1)  # Brief pause after scroll
            button.click()
            print("Button clicked successfully, waiting 2s for response...")
            time.sleep(2)
            return True
        except TimeoutException:
            print(f"Button not found or not clickable: {selector}")
            return False
        except Exception as e:
            print(f"Error clicking button: {str(e)}")
            return False

    def find_max_button(self, selector: str = "#dateSpansDiv"):
        """Find the button that selects the maximum date range and return the CSS selector for it."""
        try:
            buts = self.page_soup.select_one(selector)
            i = 1
            for res in buts.find_all("a"):
                #print(res.text)
                if res.text.upper() == "MAX":
                    max_selector = res.get("class")
                    if isinstance(max_selector, list):
                        max_selector = max_selector[0]
                    fin_selector = "a." + max_selector + f":nth-child({i})"
                    print(fin_selector)
                i += 1
            
            return fin_selector
        except Exception as e:
            print(f"Error finding date spans buttons: {str(e)}")
            return None

    def get_element(self, selector: str = ".highcharts-series path", selector_type=By.CSS_SELECTOR):
        """Find element by selector"""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((selector_type, selector))
            )
            self.current_element = element
            return element
        except TimeoutException:
            print(f"Element not found: {selector}")
            return None
        except Exception as e:
            print(f"Error finding element: {str(e)}")
            return None
        
    def series_from_element(self, element: str = None, invert_the_series: bool = True):
        """Extract series data from element text. This extracts the plotted series from the svg chart by taking the PATH 
        element of the data tarace on the chart. Series values are pixel co-ordinates on the chart.

        **Parameters:**

        - element (str): The element to extract data from. Will use self.current_element if not provided.
        - invert_the_series (bool): Whether to invert the series values.

        **Returns:**

        - series (pd.Series): The extracted series data.
        """

        if element is None:
            element = self.current_element
        
        datastrlist = element.get_attribute("d").split(" ")
        ser = pd.Series(datastrlist)
        ser_num = pd.to_numeric(ser, errors='coerce').dropna()

        exvals = ser_num[::2]; yvals = ser_num[1::2]
        exvals = exvals.sort_values().to_list()
        yvals = yvals.to_list()
        series = pd.Series(yvals, index = exvals, name = "Extracted Series")

        if invert_the_series:
            series = invert_series(series, max_val = self.y_axis.index.max())
        self.series = series

        self.pix0 = self.series.iloc[0]; self.pix1 = self.series.iloc[-1]
        return series
    
    def get_datamax_min(self):
        """Get the max and min data values for the series using y-axis values..."""
        
        print("axisY0 = ", self.y_axis.iloc[0], "axisY1 =", self.y_axis.iloc[-1])
        px_range = self.y_axis.index[-1] - self.y_axis.index[0]
        labrange = self.y_axis.iloc[-1] - self.y_axis.iloc[0]
        self.unit_per_pix_alt2 = labrange/px_range
        print("unit_per_pix: ", self.unit_per_pix)
        self.datamax = round(self.y_axis.iloc[-1] - (self.y_axis.index[-1] - self.series.max())*self.unit_per_pix, 3)
        self.datamin = round(self.y_axis.iloc[0] + (self.series.min()-self.y_axis.index[0])*self.unit_per_pix, 3)
        print("datamax: ", self.datamax, "datamin: ", self.datamin)
        return self.datamax, self.datamin
    
    def scale_series(self, right_way_up: bool = True):
        """Scale the series using the first and last values from the series pulled from the tooltip box."""

        if not right_way_up:
            max_val = self.y_axis.index.max()  # This should be the top pixel of the chart.
            self.series = invert_series(self.series, max_val = max_val)

        if hasattr(self, "start_end"):
            y0 = self.start_end["start_value"]; y1 = self.start_end["end_value"]
            pix0 = self.series.iloc[0]; pix1 = self.series.iloc[-1]
            print("Start value, end value", y0, y1, "pix0, pix1", pix0, pix1)
            
            self.unit_per_px_alt = abs(y1 - y0) / abs(pix1 - pix0)  # Calculated from the start and end datapoints.
            
            if not hasattr(self, "axis_limits"):
                self.axis_limits = self.extract_axis_limits()
            ## Turns out that this formulation below is the best way to calculate the scaling factor for the chart.
            axlims_upp = (self.y_axis.iloc[-1] - self.y_axis.iloc[0]) / (self.axis_limits["y_max"] - self.axis_limits["y_min"])

            # if the start and end points are at similar values this will be problematic though. 
            print("Start value, end value", y0, y1, " pix0, pix1", pix0, pix1, 
                  "data units perchar pixel from start & end points: ", self.unit_per_px_alt, "\n", 
                  "unit_per_pix calculated from the y axis ticks: ", self.unit_per_pix, "\n",
                  "inverse of that: ", 1/self.unit_per_pix, "\n", 
                  "unit_per_pix from axis limits and self.y_axis (probably best way): ", axlims_upp)

            self.unscaled_series = self.series.copy()
            ##Does the Y axis cross zero? Where is the zero point??
            x_intercept = find_zero_crossing(self.series)

            if x_intercept:
                print("Y axis Series does cross zero at: ", x_intercept)
                pix0 = x_intercept

            for i in range(len(self.series)):
                self.series.iloc[i] = (self.series.iloc[i] - pix0)*axlims_upp + y0
    
            self.series = self.series
        else:
            print("start_end not found, run get_datamax_min() first.")
            return

        return self.series
    
    def get_xlims_from_tooltips(self, force_rerun: bool = False):
        """ Use the get_tooltip class to get the start and end dates of the time series using the tooltip box displayed on the chart."""
        if hasattr(self, "tooltip_scraper"):
            pass    
        else: 
            self.tooltip_scraper = get_tooltip(driver=self.driver, chart_x=335.5, chart_y=677.0)  #Note: update this later to use self.width and height etc...
        
        if hasattr(self, "start_end") and self.start_end is not None and hasattr(self, "frequency") and self.frequency is not None and not force_rerun:
            return
        else:
            time.sleep(1)
            data_points, num_points = self.tooltip_scraper.scrape_dates_from_tooltips(num_points=8)
            dates = [point["date"] for point in data_points]
            values = [point["value"] for point in data_points]
            self.ripped_points = {"dates": dates, "values": values}
            #print("Dates and values scraped from tooltips: ", self.ripped_points)

            if len(data_points) > num_points and "start_date" in data_points[0].keys() and "end_date" in data_points[-1].keys():
                print("Successfully scraped start and end dates and a bunch of other points to determine frequency of time-series...")
                dates = [point["date"] for point in data_points[1:-2]]
                return data_points, dates
            self.start_end = {
                'start_date': dates[0],
                'end_date': dates[-1],
                'start_value': data_points[0]["value"], 
                'end_value': data_points[-1]["value"]
            }

            #print("These are your dates dawg.......", dates)
            diff = pd.Series(dates).diff().dropna().mode()[0]
            self.frequency = map_frequency(diff)
            print(f"\n\nTime series frequency appears to be: {diff.days}, {self.frequency}\n\n")

    def make_x_index(self, force_rerun: bool = False):
        """Make the DateTime Index for the series using the start and end dates scraped from the tooltips. 
        This does a few things and uses Selenium to scrape the dates from the tooltips on the chart as well as
        some more points to detrmine the frequency of the time series. It will take some time....
        """
        
        print("Using selenium and toltip scraping to construct the date time index for the time-series, this'll take a bit...")
        self.get_xlims_from_tooltips(force_rerun = force_rerun)

        if self.start_end is not None:
            print("Start and end values scraped from tooltips: ", self.start_end)
        else:
            print("Error: Start and end values not found...pulling out....")
            return None

        print("Creating date index for self.series, using start and end dates from tooltips stored in self.start_end.")
        try:
            start_date = self.start_end["start_date"]; end_date = self.start_end["end_date"]
            dtIndex = self.dtIndex(start_date=start_date, end_date=end_date, ser_name=self.series_name)
            print("Date index created successfully. Take a look at the final series: \n\n", dtIndex)
            return dtIndex.index
        
        except Exception as e:
            print(f"Error creating date index: {str(e)}")
       
    def get_y_axis(self):
        """Get y-axis values from chart to make a y-axis series with tick labels and positions (pixel positions).
        Also gets the limits of both axis in pixel co-ordinates. """

        ##Get positions of y-axis gridlines
        y_heights = []
        self.full_chart = self.get_element(selector = "#chart").get_attribute("outerHTML")
        self.chart_soup = BeautifulSoup(self.full_chart, 'html.parser')
        ygrid = self.chart_soup.select('g.highcharts-grid.highcharts-yaxis-grid')
        gridlines = ygrid[1].findAll('path')
        for line in gridlines:
            y_heights.append(float(line.get('d').split(' ')[-1]))
        y_heights = sorted(y_heights)

        ##Get y-axis labels
        yax = self.chart_soup.select('g.highcharts-axis-labels.highcharts-yaxis-labels')
        textels = yax[1].find_all('text')

        # Replace metrc prefixes:
        yaxlabs = [convert_metric_prefix(text.get_text()) if text.get_text().replace(',','').replace('.','').replace('-','').replace(' ','').isalnum() else text.get_text() for text in textels]
        print("y-axis labels: ", yaxlabs)

        # convert to float...
        if any(isinstance(i, str) for i in yaxlabs):
            yaxlabs = [float(''.join(filter(str.isdigit, i.replace(",", "")))) if isinstance(i, str) else i for i in yaxlabs]
        pixheights = [float(height) for height in y_heights]
        pixheights.sort()

        ##Get px per unit for y-axis
        pxPerUnit = [abs((yaxlabs[i+1]- yaxlabs[i])/(pixheights[i+1]- pixheights[i])) for i in range(len(pixheights)-1)]
        average = sum(pxPerUnit)/len(pxPerUnit)
        self.unit_per_pix = average
        print("Average px per unit for y-axis: ", average)  #Calculate the scaling for the chart so we can convert pixel co-ordinates to data values.

        yaxis = pd.Series(yaxlabs, index = pixheights, name = "ytick_label")
        yaxis.index.rename("pixheight", inplace = True)
        try:
            yaxis = yaxis.astype(int)
        except:
            pass

        self.y_axis = yaxis
        self.axis_limits = self.extract_axis_limits()
        return yaxis
    
    def dtIndex(self, start_date: str, end_date: str, ser_name: str = "Time-series"):
        """

        Create a date index for your series in self.series. Will first make an index to cover the full length of your series 
        and then resample to month start freq to match the format on Trading Economics.
        
        **Parameters:**
        - start_date (str) YYYY-MM-DD: The start date of your series
        - end_date (str) YYYY-MM-DD: The end date of your series
        - ser_name (str): The name TO GIVE the series
        """

        dtIndex = pd.date_range(start = start_date, end=end_date, periods=len(self.series))
        new_ser = pd.Series(self.series.to_list(), index = dtIndex, name = ser_name)
        if hasattr(self, "frequency"):
            new_ser = new_ser.resample(self.frequency).first()
        else:
            new_ser = new_ser.resample("MS").first()  ## Use First to match the MS freq.
        self.series = new_ser
        return new_ser

    def extract_axis_limits(self):
        """Extract axis limits from the chart in terms of pixel co-ordinates."""
        try:
            # Extract axis elements
            yax = self.chart_soup.select_one("g.highcharts-axis.highcharts-yaxis path.highcharts-axis-line")
            xax = self.chart_soup.select_one("g.highcharts-axis.highcharts-xaxis path.highcharts-axis-line")
            
            ylims = yax["d"].replace("M", "").replace("L", "").strip().split(" ")
            ylims = [float(num) for num in ylims if len(num) > 0][1::2]
            print("yax: ", ylims)

            xlims = xax["d"].replace("M", "").replace("L", "").strip().split(" ")
            xlims = [float(num) for num in xlims if len(num) > 0][0::2]
            print("xax: ", xlims)
            
            axis_limits = {
                'x_min': xlims[0],
                'x_max': xlims[1],
                'y_min': ylims[0],
                'y_max': ylims[1]
            }
            
            return axis_limits
        except Exception as e:
            print(f"Error extracting axis limits: {str(e)}")
            return None
    
    def plot_series(self, add_horizontal_lines: bool = False):
        fig = self.series.plot()

        if hasattr(self, "series_metadata"):
            title = str(self.series_metadata["country"]).capitalize() + ": " + str(self.series_metadata["title"]).capitalize()
            ylabel = str(self.series_metadata["units"]).capitalize()
        else:
            title = "Time Series Plot"; ylabel = "Value"

        if add_horizontal_lines:
            # Add horizontal lines and labels
            for i in range(len(self.y_axis)):
                fig.add_shape(
                    type='line',
                    x0=self.series.index.min(),
                    y0=self.y_axis.index[i],
                    x1=self.series.index.max(),
                    y1=self.y_axis.index[i],
                    line=dict(color='Red', dash='dash')
                )
                fig.add_annotation(
                    x=self.series.index.max(),  # Position the label at the end of the line
                    y=self.y_axis.index[i],
                    text=str(self.y_axis.iloc[i]),
                    showarrow=False,
                    xanchor='left',
                    yanchor='middle'
                )

        # Label x and y axis
        fig.update_layout(
            legend=dict(
            title_text="",  # Remove legend title
            orientation="h",
            yanchor="bottom",
            y=-0.2,  # Adjust this value to move the legend further down
            xanchor="center",
            x=0.5
            ),
            yaxis_title=ylabel,
            xaxis_title="",
            title = title
        )
  
        # Show the figure
        fig.show()

    def scrape_metadata(self):
        self.series_metadata = {}

        try:
            self.series_metadata["units"] = self.chart_soup.select_one('#singleIndChartUnit2').text
        except Exception as e:
            print("Units label not found: ", {str(e)})
            self.series_metadata["units"] = "a.u"
        
        try:
            self.series_metadata["original_source"] = self.chart_soup.select_one('#singleIndChartUnit').text
        except Exception as e:
            print("original_source label not found: ", {str(e)})
            self.series_metadata["original_source"] = "unknown"

        if hasattr(self, "series"):
            if hasattr(self, "page_soup"):
                heads = self.page_soup.select("#ctl00_Head1")
                self.series_metadata["title"] = heads[0].title.text.strip()
            else:
                self.series_metadata["title"] = self.last_url.split("/")[-1].replace("-", " ")  # Use URL if can't find the title
            self.series_metadata["country"] = self.last_url.split("/")[-2].replace("-", " ")  # Placeholder for now
            self.series_metadata["length"] = len(self.series)
            self.series_metadata["frequency"] = self.frequency  # Placeholder for now
            self.series_metadata["source"] = "Trading Economics"  # Placeholder for now
            self.series_metadata["id"] = "/".join(self.last_url.split("/")[-2:])
            self.series_metadata["start_date"] = self.series.index[0].strftime("%Y-%m-%d")
            self.series_metadata["end_date"] = self.series.index[-1].strftime("%Y-%m-%d")
            self.series_metadata["min_value"] = float(self.series.min())
            self.series_metadata["max_value"] = float(self.series.max())
            print("Series metadata: ", self.series_metadata)

        try:
            desc_card = self.page_soup.select_one("#item_definition")
            header_text = desc_card.select_one('.card-header').text.strip()
            if header_text.lower() == self.series_metadata["title"].lower():
                self.series_metadata["description"] = desc_card.select_one('.card-body').text.strip()
            else:
                print("Description card title does not match series title.")
                self.series_metadata["description"] = "Description not found."
        except Exception as e:
            print("Description card not found: ", {str(e)})

    def get_page_source(self):
        """Get current page source after interactions"""
        return self.driver.page_source
    
    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


############ Convenience function to run the full scraper ##########################################

def scrape_chart(url: str, driver: webdriver = None, headless: bool = True, browser: str = 'firefox') -> TE_Scraper:
    """ This convenience function will scrape a chart from Trading Economics and return a TE_Scraper object with the series data.

    ** Parameters: **

    - url (str): The URL of the chart to scrape.
    - headless (bool): Whether to run the browser in headless mode.
    - browser (str): The browser to use, either 'chrome' or 'firefox'.

    ** Returns: **  
    - TE_Scraper object with the scraped data or None if an error occurs.
    """

    loaded_page = False; clicked_button = False; yaxis = None; series = None; x_index = None; scaled_series = None; datamax = None; datamin = None

    sel = TE_Scraper(driver = driver, browser = browser, headless = headless)
    if sel.load_page(url):
        print("Page at ", url, ", loaded successfully.")
        loaded_page = True
    else:
        print("Error loading page at: ", url)
        return None

    if sel.click_button(sel.find_max_button()):  ## This is the "MAX" button on the Trading Economics chart to set the chart to max length.
        print("Clicked the MAX button successfully.")
        clicked_button = True
    else:
        print("Error clicking the MAX button.")
        return None
    
    time.sleep(2)
    try:
        yaxis = sel.get_y_axis()
        print("Successfully scraped y-axis values from the chart:", " \n", yaxis)  
    except Exception as e:
        print(f"Error scraping y-axis: {str(e)}")
    
    try:
        sel.get_element()
        series = sel.series_from_element(invert_the_series=True)
        print("Successfully scraped raw pixel co-ordinate seruies from the path element in chart:", " \n", series)
        time.sleep(1)
    except Exception as e:
        print(f"Error scraping y-axis: {str(e)}")

    try:
        x_index = sel.make_x_index()
        time.sleep(1)
    except Exception as e:
        print(f"Error creating date index: {str(e)}")

    try:
        #datamax, datamin = sel.get_datamax_min()   
        scaled_series = sel.scale_series()   
    except Exception as e:
        print(f"Error scaling series: {str(e)}")
    
    if loaded_page and clicked_button and yaxis is not None and series is not None and x_index is not None and scaled_series is not None: #and datamax is not None and datamin is not None:
        print("Successfully scraped time-series from chart at: ", url, " \n", sel.series, "now getting some metadata...")
        sel.scrape_metadata()
        print("Check the metadata: ", sel.series_metadata, "\nScraping complete! Happy pirating yo!")

        return sel
    else:
        print("Error scraping chart at: ", url) 
        return None
        
class search_TE(object):
    """Class for searching Trading Economics website and extracting search results.
    This class is designed to search the Trading Economics website for a given term and extract the search results.
    It can load the search page, enter a search term, and extract the URLs of the search results.

    **Init Parameters:**

    - driver (webdriver): A Selenium WebDriver object, can put in an active one or make a new one for a new URL.
    - browser (str): The browser to use for scraping, either 'chrome' or 'firefox'.
    - search_term (str): The term to search for on the website.
    - headless (bool): Whether to run the browser in headless mode (show no window).
    """
    # Define browser type with allowed values
    BrowserType = Literal["chrome", "firefox"]
    
    def __init__(self, driver: webdriver = None, 
                 browser: BrowserType = "firefox", 
                 search_term: str = "US ISM Services PMI",
                 headless: bool = True):
        
        self.browser = browser
        self.headless = headless

        if driver is None:
            if browser == "chrome":
                options = webdriver.ChromeOptions()
                if headless:
                    options.add_argument('--headless')
                self.driver = webdriver.Chrome(options=options)
            elif browser == "firefox":
                options = webdriver.FirefoxOptions()
                if headless:
                    options.add_argument('--headless')
                self.driver = webdriver.Firefox(options=options)
            else:
                raise ValueError("Unsupported browser! Use 'chrome' or 'firefox'.")
        else:
            self.driver = driver

        self.search_term = search_term
        self.home_page()

    def home_page(self):
        """Load the Trading Economics home page."""
        # Load page
        try:
            print("Loading home page...")
            self.driver.get("https://tradingeconomics.com/")
        except Exception as e:
            print(f"Error occurred: {str(e)}")

    def search_trading_economics(self, search_term: str = None):
        """Search Trading Economics website for a given term and extract URLs of search results.
        This method will search the Trading Economics website for a given term and extract the URLs of the search results.
        It will enter the search term in the search box, submit the search, and extract the URLs of the search results.
        Results are assigned to the 'results' attribute as a list of URLs and as result_table attribute as a pandas df.

        **Parameters:**

        - search_term (str): The term to search for on the website.
        """

        self.current_page = self.driver.current_url
        if self.current_page != "https://tradingeconomics.com/":
            self.home_page()
            time.sleep(2)
 
        if search_term is None:
            search_term = self.search_term
        else:
            self.search_term = search_term
        
        try:
        # Wait for search box - using the ID from the HTML
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "thisIstheSearchBoxIdTag")))
   
            
            # Click search box
            print("Clicking search box...")
            search_box.click()
            
            # Enter search term
            print(f"Entering search term: {search_term}")
            search_box.send_keys(search_term)
            time.sleep(1)  # Small delay to let suggestions appear
            
            # Press Enter
            print("Submitting search...")
            search_box.send_keys(Keys.RETURN)
            
            # Wait a moment to see results
            time.sleep(3)

            self.results = self.extract_search_results(self.driver.page_source)
            self.results_table()
        
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            return None
        
    def extract_search_results(self, html_content):
        """Extract URLs from search results page"""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all list items in search results
        results = soup.find_all('li', class_='list-group-item')
        
        urls = []
        for result in results:
            # Find the main link in each result item
            link = result.find('a', href=True)
            if link and link['href'].startswith('/'):
                full_url = f"https://tradingeconomics.com{link['href']}"
                urls.append(full_url)
        
        return urls
    
    def results_table(self):
        """Create a DataFrame from the search results"""

        if hasattr(self, "results"):
            metrics = []
            countries = []
            for result in self.results:
                metrics.append(result.split("/")[-1].replace("-", " "))
                countries.append(result.split("/")[-2].replace("-", " "))
            df = pd.DataFrame({'country': countries, 'metric': metrics, "url": self.results})
            df.index.rename('result', inplace=True)
            self.result_table = df
        else:
            print("No search results found.")
            return None
        
    def get_data(self, result_num: int = 0):
        """Scrape data for a given search result number.
        This method will scrape data for a given search result number from the search results table.
        It will extract the URL for the result and scrape the data from the chart at that URL.
        The scraped data is assigned to the 'scraped_data' attribute as a TE_scraper object.
        This will use the TE_Scraper class and methods to scrape the data from the Trading Economics website.
        
        **Parameters:**
        - result_num (int): The index of the search result in your result tabel to scrape the data for.

        **Returns:**
        - scraped_data (TE_Scraper): The scraped data object. The data can be accessed from the 'series' attribute of the object.
        """

        print("Attempting to scrape data for result ", result_num, ", ", self.result_table.loc[result_num, "country"], self.result_table.loc[result_num, "metric"] )
        if hasattr(self, "result_table"):
            url = self.result_table.loc[result_num, "url"]
            print(f"Scraping data from: {url}")
            self.scraped_data = scrape_chart(url, driver = self.driver, headless=self.headless, browser=self.browser)
            return self.scraped_data
        else:
            print("No search results found.")
            return None
  
if __name__ == "__main__":

    sickie = get_tooltip()
    sickie.bail_out()
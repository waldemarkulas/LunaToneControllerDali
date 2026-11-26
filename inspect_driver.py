from dali.driver.serial import DriverLubaRs232

driver = DriverLubaRs232(uri="luba232:COM4")

for name in dir(driver):
    if not name.startswith("_"):
        print(name)

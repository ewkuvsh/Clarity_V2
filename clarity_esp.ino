#include <Wire.h>
#include <Adafruit_NeoPixel.h>

#define I2C_SLAVE_ADDRESS 0x28  
#define PIN 1          
#define NUMPIXELS 1      

Adafruit_NeoPixel strip(NUMPIXELS, PIN, NEO_GRB + NEO_KHZ800);

void setup() {
  strip.begin();
  strip.setBrightness(50);
  strip.setPixelColor(0, strip.Color(255, 0, 0));
  strip.show();  
 
  Wire.begin(I2C_SLAVE_ADDRESS);
  Wire.onReceive(onReceive);  
}

void loop() {
  delay(100);
}

void onReceive(int numBytes) {
  while (Wire.available()) {
    char data = Wire.read();
    
    if(data == 'w') {
      // White
      strip.setPixelColor(0, strip.Color(255, 255, 255));
      strip.show();
    }
    else if(data == 'g') {
      // Green
      strip.setPixelColor(0, strip.Color(0, 255, 0));
      strip.show();
    }
    else if(data == 'b') {
      // Blue
      strip.setPixelColor(0, strip.Color(0, 0, 255));
      strip.show();
    }
    else if(data == 'r') {
      // Red
      strip.setPixelColor(0, strip.Color(255, 0, 0));
      strip.show();
    }
    else if(data == 'y') {
      // Yellow
      strip.setPixelColor(0, strip.Color(255, 255, 0));
      strip.show();
    }
    else if(data == 'c') {
      // Cyan
      strip.setPixelColor(0, strip.Color(0, 255, 255));
      strip.show();
    }
    else if(data == 'm') {
      // Magenta
      strip.setPixelColor(0, strip.Color(255, 0, 255));
      strip.show();
    }
    else if(data == 'p') {
      // Purple
      strip.setPixelColor(0, strip.Color(128, 0, 128));
      strip.show();
    }
    else if(data == 'o') {
      // Orange
      strip.setPixelColor(0, strip.Color(255, 165, 0));
      strip.show();
    }
  }
}
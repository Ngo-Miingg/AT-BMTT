#include <iostream>
#include <map>
#include <cmath>
#include <string>
using namespace std;

// Hàm tính entropy
double calculate_entropy(const string& text) {
    map<char, int> freq;
    for (char c : text) freq[c]++;

    double entropy = 0.0;
    for (auto& pair : freq) {
        double p = (double)pair.second / text.size();
        entropy -= p * log2(p);
    }
    return entropy;
}

// Hàm tính độ dư thừa thông tin
double calculate_redundancy(double entropy, int N = 256) {
    double max_entropy = log2(N);
    return max_entropy - entropy;
}

int main() {
    string input;
    cout << "Enter a string of characters: ";
    getline(cin, input);

    double H = calculate_entropy(input);
    double R = calculate_redundancy(H);

    cout << "Entropy: " << H << endl;
    cout << "Redundancy: " << R << endl;

    return 0;
}

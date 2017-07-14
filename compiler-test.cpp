#include <iostream>
#include <vector>
#include <algorithm>
#include <numeric>
#include <future>
#include <chrono>
#include <cstdlib>
 
template <typename RAIter>
int parallel_sum(RAIter beg, RAIter end)
{
    auto len = end - beg;
    if (len < 1000)
        return std::accumulate(beg, end, 0);
 
    RAIter mid = beg + len/2;
    auto handle = std::async(std::launch::async,
                             parallel_sum<RAIter>, mid, end);
    int sum = parallel_sum(beg, mid);
    return sum + handle.get();
}
 
int main(int argc, char* argv[])
{
	int expected_value = 500000;
	if (argc >= 2) {
		expected_value = std::atoi(argv[1]);
	}
    std::vector<int> v(expected_value, 1);
	std::cout<< "Expected sum: " << expected_value << std::endl;
	
	std::chrono::time_point<std::chrono::system_clock> start, end;
	std::cout<< "Summing with std::async..." << std::endl;
	start = std::chrono::system_clock::now();
	std::cout << "With std::async " << parallel_sum(v.begin(), v.end()) << std::endl;
	end = std::chrono::system_clock::now();
	std::chrono::duration<double> elapsed_seconds = end-start;
	std::cout<< "Consumed time: " << elapsed_seconds.count() << "s" << std::endl;
	
	std::cout<< "Summing with std::accumulate..." << std::endl;
	start = std::chrono::system_clock::now();
	std::cout << "With std::accumulate " << std::accumulate(v.begin(), v.end(), 0) << std::endl;
	end = std::chrono::system_clock::now();
	elapsed_seconds = end-start;
	std::cout<< "Consumed time: " << elapsed_seconds.count() << "s" << std::endl;
	return 0;
}
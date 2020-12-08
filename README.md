# # CS 410 Course Project: Improving a System - Collaborative Filtering with Social Exposure: A Modular Approach to Social Recommendation

## Overview
Our project is improving the recommendation algorithm discussed in this [paper](https://arxiv.org/pdf/1711.11458.pdf). To improve this system, we built on an existing recommendation system called [RecQ](https://github.com/Coder-Yu/RecQ). This system provides a host of different recommendation algorithms and datasets to test them on, including the one proposed in this paper.

## Software Implementation
For information about the implementation and architecture of the entire RecQ system, please refer to the original repository. Our implementations build on the architecture of this system by adding our custom algorithm extensions to the RecQ framework.

## Development Environment Setup
1. Install [miniconda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/)
2. Create a new miniconda environment with Python 2.7
3. Run `conda install mkl-source`
4. Clone this repository
5. Activate the environment and install dependencies with `pip install -r requirements`
6. Run `python main.py`
7. Follow the prompt and entire the desired algorithm to run

## Usage
The original SERec boost algorithm discussed in the paper can be run by inputing the corresponding value ("s10") for the SERec algorithm. Similarly, each of our individual extensions can be run by inputting the corresponding value displayed in the prompt. 

## Team Member Contributions

### Philip Cori
I implemented an algorithm for measuring friend closeness, which is a suggested extension mentioned in the original paper. To measure friend closeness, I use the formula:

closeness = n / m * 100, where n is the number of mutual friends between the two friends, and m is total number of friends between the two friends. The result is multiplied by 100 to speed up the convergence speed.

The intuition behind this is that it would seem two friends are closer friends if they share many mutual friends. Furthermore, two friends are considered closer if they have less total friends, which gives more weight to their own friendship.
